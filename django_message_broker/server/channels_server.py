import asyncio
from asyncio.futures import Future
from datetime import datetime, timedelta
from tornado.ioloop import IOLoop, PeriodicCallback
from typing import Callable, Dict, List, Optional, Union
import zmq

from .server_queue import ChannelQueue, Endpoint
from .data_message import DataMessage, DataMessageCommands
from .exceptions import (
    ChannelsServerError,
    MessageCommandUnknown,
    SubscriptionError,
    MessageFormatException,
)
from .signalling_message import SignallingMessage, SignallingMessageCommands
from .socket_manager import SocketManager


class ChannelsServer:
    """Message server for Django Channels.

    Implements a network message server for Django channels using zero message queue (ZMQ) to
    support communication between channels registered within different processes.

    The server opens two sequential ports:

    + Data port (base port, default=5556): Transmission of data messages between the client and server.

    + Signalling port (base port + 1, default=5557): Transmission of signalling messages between the client and server.
    """

    def __init__(self, ip_address: str = "127.0.0.1", port: int = 5556):
        """Message server for Django Channels.

        Args:
            ip_address (str, optional): IP address to which sockets bind. Defaults to "127.0.0.1".
            port (int, optional): Base port for the server. Defaults to 5556.

        Raises:
            ChannelsServerError: Raised when an error occurs within the server.
        """
        # Create message store and groups store.
        self.message_store: Dict[bytes, ChannelQueue] = {}
        self.group_store: Dict[bytes, Dict[bytes, datetime]] = {}

        # Create zmq context, event loop and sockets
        # Note the server uses the zmq context
        self.port = port
        self.ctx = zmq.Context()
        self.core_event_loop = IOLoop.instance()

        try:
            self.data_port = SocketManager(
                self.ctx, ip_address, self.port, is_server=True
            )
            self.data_port.set_receive_callback(self._receive_data)
        except ChannelsServerError:
            raise ChannelsServerError("Unable to create server data socket")

        try:
            self.signalling_port = SocketManager(
                self.ctx, ip_address, self.port + 1, is_server=True
            )
            self.signalling_port.set_receive_callback(self.receive_signalling)
        except ChannelsServerError:
            raise ChannelsServerError("Unable to create server signalling socket")

        # Establish callbacks to flush stale queues and groups.
        self.flush_queues_callback = PeriodicCallback(
            self._flush_queues, callback_time=5000, jitter=0.1
        )
        self.flush_groups_callback = PeriodicCallback(
            self._flush_groups, callback_time=5000, jitter=0.1
        )

        # Create dictionary of data message command methods.
        self.data_msg_calls: Dict[bytes, Callable[[DataMessage], None]] = {}
        self.data_msg_calls[DataMessageCommands.SUBSCRIBE] = self._subscribe
        self.data_msg_calls[DataMessageCommands.SEND_TO_CHANNEL] = self._send_to_channel
        self.data_msg_calls[DataMessageCommands.SEND_TO_GROUP] = self._send_to_group
        self.data_msg_calls[DataMessageCommands.KEEPALIVE] = self._no_operation

        # Create dictionary of signalling message command methods.
        self.sig_msg_calls: Dict[bytes, Callable[[SignallingMessage], None]] = {}
        self.sig_msg_calls[SignallingMessageCommands.GROUP_ADD] = self._group_add
        self.sig_msg_calls[
            SignallingMessageCommands.GROUP_DISCARD
        ] = self._group_discard
        self.sig_msg_calls[SignallingMessageCommands.FLUSH] = self._flush_all
        self.sig_msg_calls[SignallingMessageCommands.PRINT] = self._print
        self.sig_msg_calls[SignallingMessageCommands.PERFORMANCE] = self._no_operation
        self.sig_msg_calls[SignallingMessageCommands.KEEPALIVE] = self._no_operation

    def start(self) -> None:
        """Start the channels server.

        Raises:
            ChannelsServerError: If the server cannot be started.
        """
        try:
            self.data_port.start()
            self.signalling_port.start()
            self.flush_queues_callback.start()
            self.flush_groups_callback.start()

            self.core_event_loop.start()

        except Exception as exception:
            raise ChannelsServerError(
                f"Exception whilst starting channels server.\n{exception}"
            )

    def stop(self) -> None:
        """Stop the channels server."""
        try:
            self.flush_groups_callback.stop()
            self.flush_queues_callback.stop()

            self.core_event_loop.stop()

            self.signalling_port.stop()
            self.data_port.stop()
        except Exception as exception:
            raise ChannelsServerError(
                f"Exception whilst stopping channels server.\n{exception}"
            )

    def _receive_data(self, multipart_message: Union[Future, List]) -> None:
        """Callback raised when a message is received on the data port. Parses the message to
        identify the relevant command and dispatches the messages to the relevant command handler.

        Args:
            multipart_message (Union[Future, List]): Multipart message received on data port.

        Raises:
            ImportError: Error raised if the multitpart message cannot be parsed to a valid data message.
            MessageCommandUnknown: The command in the message is unknown.
        """
        try:
            message = DataMessage.from_msg(multipart_message, unpack_body=False)
        except Exception as exception:
            raise ImportError(exception)

        command = message.command
        if command:
            call_function = self.data_msg_calls.get(command)
            if call_function:
                call_function(message)
            else:
                raise MessageCommandUnknown(f"{command} is unknown. {message}")
        else:
            MessageCommandUnknown("No command sent with the message. {message}")

    def _subscribe(self, message: DataMessage) -> None:
        """Command handler for SUBCHANX: Subscribe to a channel.

        Registers an endpoint as a subscriber to a channel. If the channel doesn't exist then it creates
        a new channel.

        Args:
            message (DataMessage): Message received requesting subscription to the channel.
        """
        subscriber_name = message["subscriber_name"]
        try:
            _ = message.channel_name.decode("utf-8").index("!")
            is_process_channel = True
        except ValueError:
            is_process_channel = False

        endpoint = Endpoint(
            socket=self.data_port.get_socket(),
            dealer=message.endpoints,
            subscriber_name=subscriber_name,
            is_process_channel=is_process_channel,
        )
        channel_name = message.channel_name
        try:
            channel_queue = self.message_store.get(channel_name)
            if channel_queue is None:
                channel_queue = ChannelQueue(channel_name=channel_name)
                self.message_store[channel_name] = channel_queue

            channel_queue.subscribe(endpoint)

        except SubscriptionError as exception:
            subscription_error = message
            subscription_error.command = DataMessageCommands.SUBSCRIPTION_ERROR
            subscription_error.properties = {"exception": repr(exception)}
            asyncio.create_task(subscription_error.send(self.data_port.get_socket()))

    def _send_to_channel(self, message: DataMessage) -> None:
        """Command handler for SENDCHAN: Send message to a channel.

        Creates a new queue if one does not exist. Adds the message to the queue.

        If the "ttl" property is set on the message then set the expiry time of the message.

        Args:
            message (DataMessage): Received data message.
        """
        # DO NOT use setdefault to create a new channel. Setdefault always creates a new
        # ChannelQueue object each time the function is called (ALL parameters to a function are calculated
        # before the function is evaluated), therefore, it creates a new default object even if the
        # key exists in the dictionary. When a ChannelQueue object is initialised it spawns a task on
        # the event loop, however, if the key already exists and the ChannelQueue object is not used,
        # then the spawned event loop in ChannelQueue is not stopped and the object is not deleted (The
        # task creates a reference to the ChannelQueue object so the reference count never drops to zero
        # and __del__ is never called). This creates a memory leak which persists until the message store
        # is flushed, at which point the tasks will terminate in such a way that the CancelledError exceptions
        # cannot be caught.
        channel_name = message.channel_name
        channel_queue = self.message_store.get(channel_name)
        if channel_queue is None:
            channel_queue = ChannelQueue(channel_name=channel_name)
            self.message_store[channel_name] = channel_queue
        try:
            time_to_live: float = int(message["ttl"])
        except (KeyError, ValueError):
            time_to_live: float = 60
        channel_queue.push(message, time_to_live=time_to_live)

    def _send_to_group(self, message: DataMessage) -> None:
        """Command handler for SENDGRPX: Send message to a group.

        Sends a message to a group of channels. The method creates a quick copy of the data message
        and pushes it to each channel. The shallow copy share the body of the message between all
        copies to reduce encoding/decoding times and memory utilisation.

        Args:
            message (DataMessage): Received data message.
        """
        group_name = message.channel_name
        channel_names = self.group_store.get(group_name, {})
        for channel_name in channel_names.keys():
            channel_message = message.quick_copy()
            channel_message.channel_name = channel_name
            channel_message.command = DataMessageCommands.SEND_TO_CHANNEL
            self._send_to_channel(channel_message)

    def receive_signalling(self, multipart_message: Union[Future, List]) -> None:
        """Callback raised when a message is received on the signalling port. Parses the message to
        identify the relevant command and dispatches the messages to the relevant command handler.

        Args:
            multipart_message (Union[Future, List]): Multipart message received on data port.

        Raises:
            ImportError: Error raised if the multitpart message cannot be parsed to a valid data message.
            MessageCommandUnknown: The command in the message is unknown.
        """
        try:
            message = SignallingMessage.from_msg(multipart_message)
        except MessageFormatException:
            message = None

        if message:
            try:
                command = message.command
                if command:
                    call_function = self.sig_msg_calls.get(command)
                    if call_function:
                        call_function(message)
                        message.command = SignallingMessageCommands.COMPLETE
                    else:
                        raise MessageCommandUnknown(f"{command} is unknown. {message}")
                else:
                    raise MessageCommandUnknown(
                        "No command sent with the message. {message}"
                    )
            except Exception as exception:
                message.command = SignallingMessageCommands.EXCEPTION
                message.properties["exception"] = repr(exception)

            asyncio.create_task(message.send(self.signalling_port.get_socket()))

    def _group_add(self, message: SignallingMessage) -> None:
        """Command handler for GROUPADD: Add channel to group.

        Adds a channel to a group. Creates the group if it does not exist.

        If the ttl property is set then sets the expiry time of the group (default is 1 day)

        Args:
            message (DataMessage): Received data message.
        """
        group: Optional[Union[str, bytes]] = message.properties.get("group_name")
        channel: Optional[Union[str, bytes]] = message.properties.get("channel_name")
        time_to_live: float = message.properties.get("ttl", 86400)

        if group and channel:
            group_as_bytes = (
                bytes(group.encode("utf8")) if isinstance(group, str) else group
            )
            channel_as_bytes = (
                bytes(channel.encode("utf8")) if isinstance(channel, str) else channel
            )
            group_entry = self.group_store.get(group_as_bytes)
            if group_entry is None:
                group_entry = {}
            group_entry[channel_as_bytes] = datetime.now() + timedelta(
                seconds=time_to_live
            )
            self.group_store[group_as_bytes] = group_entry

    def _group_discard(self, message: SignallingMessage) -> None:
        """Command handler for GROUPDIS: Remove channel from group.

        Removes a channel from a group.

        Args:
            message (DataMessage): Received data message.
        """
        group = message.properties.get("group_name")
        channel = message.properties.get("channel_name")
        if group and channel:
            group_as_bytes = (
                group if isinstance(group, bytes) else bytes(group.encode("utf-8"))
            )
            channel_as_bytes = (
                channel
                if isinstance(channel, bytes)
                else bytes(channel.encode("utf-8"))
            )
            group_entry = self.group_store.setdefault(group_as_bytes, {})
            try:
                del group_entry[channel_as_bytes]
            except KeyError:
                pass

    def _flush_all(self, _: SignallingMessage) -> None:
        """Command handler for FLUSHXXX: Reset the server.

        Remove all groups, subscriptions and messages from the server

        Args:
            _ (SignallingMessage): Received message (not used)
        """
        # TODO: Need to flush all client client caches as well - Track endpoints when
        # receiving signalling message. Then send to known endpoints. Purge endpoints
        # if not receiving a messages. within time-out period.
        self.message_store: Dict[bytes, ChannelQueue] = {}
        self.group_store: Dict[bytes, Dict[bytes, datetime]] = {}

    def _print(self, _: SignallingMessage) -> None:
        """Command handler for PRINTXXX: Print server contents.

        Prints the contents of the message store and group store on the terminal.

        Args:
            _ (SignallingMessage): Received message (not used)
        """
        print("--- MESSAGE STORE ---")
        for sequence, queue in self.message_store.items():
            print(sequence, ":", queue.queue)
        print("--- END MESSAGE STORE ---")
        print("--- GROUP STORE ---")
        print(self.group_store)
        print("--- END GROUP STORE ---")

    def _no_operation(self, _: Union[DataMessage, SignallingMessage]) -> None:
        """No operations called when messages are not implemented

        Args:
            _ (SignallingMessage): Dummy parameter
        """
        pass

    def _flush_queues(self) -> None:
        """Periodic callback to flush queues where there are no subscribers or messages."""
        queues = list(self.message_store.keys())
        for queue in queues:
            if self.message_store[queue].is_empty():
                del self.message_store[queue]

    def _flush_groups(self) -> None:
        """Periodic callback to flush groups that have expired."""
        for _, group in self.group_store.items():
            for channel in list(group.keys()):
                if datetime.now() > group[channel]:
                    del group[channel]
