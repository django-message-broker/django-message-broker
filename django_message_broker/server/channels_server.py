"""
Implements the Django Message Broker Server.
"""
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
)
from .signalling_message import SignallingMessage, SignallingMessageCommands
from .socket_manager import SocketManager
from .utils import MethodRegistry


class ChannelsServer:
    """Message server for Django Channels.

    Implements a network message server for Django channels using zero message queue (ZMQ) to
    support communication between channels registered within different processes.

    The server opens two sequential ports:

    + Data port (base port, default=5556): Transmission of data messages between the client and server.

    + Signalling port (base port + 1, default=5557): Transmission of signalling messages between the client and server.
    """

    class DataCommands(MethodRegistry):
        """Create registry of data commands using decorators."""

        # We need to create the registry in the subclass when there is more than one registry.
        callables: Dict[bytes, Callable] = {}

    class SignallingCommands(MethodRegistry):
        """Create registry of signalling commands using decorators."""

        # We need to create the registry in the subclass when there is more than one registry.
        callables: Dict[bytes, Callable] = {}

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

        # Create jump dictionaries to index callable methods on message commands.
        self.data_callables = ChannelsServer.DataCommands.get_bound_callables(self)
        self.signalling_callables = (
            ChannelsServer.SignallingCommands.get_bound_callables(self)
        )

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
            self.signalling_port.set_receive_callback(self._receive_signalling)
        except ChannelsServerError:
            raise ChannelsServerError("Unable to create server signalling socket")

        # Establish callbacks to flush stale queues and groups.
        self.flush_queues_callback = PeriodicCallback(
            self._flush_queues, callback_time=5000, jitter=0.1
        )
        self.flush_groups_callback = PeriodicCallback(
            self._flush_groups, callback_time=5000, jitter=0.1
        )

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

            for channel_name, channel_queue in self.message_store.items():
                channel_queue.stop()
            self.message_store: Dict[bytes, ChannelQueue] = {}
            self.group_store: Dict[bytes, Dict[bytes, datetime]] = {}

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

        If the "ack" property is set then the server will send a response to the client. There are
        three potential responses:

        * COMPLETE: The command completed successfully.
        * EXCEPTION: An exception occurred in the server.
        * COMMAND SPECIFIC: A specific response to the command generated by the server.

        Args:
            multipart_message (Union[Future, List]): Multipart message received on data port.
        """
        message = DataMessage.from_msg(multipart_message, unpack_body=False)
        response_message = None

        try:
            command = message.command
            if command:
                call_function = self.data_callables.get(command)
                if call_function:
                    response_message = call_function(message)
                else:
                    raise MessageCommandUnknown(f"{command} is unknown. {message}")
            else:
                MessageCommandUnknown("No command sent with the message. {message}")

        except Exception as exception:
            response_message = DataMessage(
                endpoints=message.endpoints.copy(),
                id=message.id,
                channel_name=message.channel_name,
                command=DataMessageCommands.EXCEPTION,
                properties={"exception": repr(exception)},
            )

        finally:
            if message.get("ack"):
                # If client requests acknowledgement and no other response has been created
                # then send response indicating task complete.
                if response_message is None:
                    response_message = DataMessage(
                        endpoints=message.endpoints.copy(),
                        id=message.id,
                        channel_name=message.channel_name,
                        command=DataMessageCommands.COMPLETE,
                    )
                asyncio.create_task(response_message.send(self.data_port.get_socket()))

    @DataCommands.register(command=DataMessageCommands.SUBSCRIBE)
    def _subscribe(self, message: DataMessage) -> None:
        """Command handler for SUBCHANX: Subscribe to a channel.

        Registers an endpoint as a subscriber to a channel. If the channel doesn't exist then it creates
        a new channel.

        Args:
            message (DataMessage): Message received requesting subscription to the channel.
        """

        try:
            subscriber_name = message["subscriber_name"]
            if subscriber_name is None:
                raise KeyError
        except KeyError:
            raise SubscriptionError("Subscriber name must be provided.")

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

        channel_queue = self.message_store.get(channel_name)
        if channel_queue is None:
            channel_queue = ChannelQueue(channel_name=channel_name, max_length=None)
            self.message_store[channel_name] = channel_queue

        channel_queue.subscribe(endpoint)

    @DataCommands.register(command=DataMessageCommands.UNSUBSCRIBE)
    def _unsubscribe(self, message: DataMessage) -> None:
        """Command handler for USUBCHAN: Unsubscribe to a channel.

        Removes an endpoint from a channel.

        Args:
            message (DataMessage): Message received requesting subscription to the channel.
        """
        try:
            subscriber_name = message["subscriber_name"]
            if subscriber_name is None:
                raise KeyError
        except KeyError:
            raise SubscriptionError("Subscriber name must be provided.")

        endpoint = Endpoint(
            socket=self.data_port.get_socket(),
            dealer=message.endpoints,
            subscriber_name=subscriber_name,
        )
        channel_name = message.channel_name
        channel_queue = self.message_store.get(channel_name)
        if channel_queue is None:
            raise SubscriptionError("Cannot unsubscribe, channel does not exist.")
        channel_queue.discard(endpoint)

    @DataCommands.register(command=DataMessageCommands.SEND_TO_CHANNEL)
    def _send_to_channel(self, message: DataMessage) -> None:
        """Command handler for SENDCHAN: Send message to a channel.

        Creates a new queue if one does not exist. Adds the message to the queue.

        If the "ttl" property is set on the message then set the expiry time of the message.

        Args:
            message (DataMessage): Received data message.
        """
        channel_name = message.channel_name
        channel_queue = self.message_store.get(channel_name)
        if channel_queue is None:
            channel_queue = ChannelQueue(channel_name=channel_name, max_length=None)
            self.message_store[channel_name] = channel_queue
        try:
            time_to_live: float = int(message["ttl"])
        except (KeyError, ValueError):
            time_to_live: float = 60
        channel_queue.push(message, time_to_live=time_to_live)

    @DataCommands.register(command=DataMessageCommands.SEND_TO_GROUP)
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

    def _receive_signalling(self, multipart_message: Union[Future, List]) -> None:
        """Callback raised when a message is received on the signalling port. Parses the message to
        identify the relevant command and dispatches the messages to the relevant command handler.

        If the "ack" property is set then the server will send a response to the client. There are
        three potential responses:

        * COMPLETE: The command completed successfully.
        * EXCEPTION: An exception occurred in the server.
        * COMMAND SPECIFIC: A specific response to the command generated by the server.

        Args:
            multipart_message (Union[Future, List]): Multipart message received on data port.

        Raises:
            ImportError: Error raised if the multitpart message cannot be parsed to a valid data message.
            MessageCommandUnknown: The command in the message is unknown.
        """
        message = SignallingMessage.from_msg(multipart_message)
        response_message = None

        try:
            command = message.command
            if command:
                call_function = self.signalling_callables.get(command)
                if call_function:
                    response_message = call_function(message)
                    message.command = SignallingMessageCommands.COMPLETE
                else:
                    raise MessageCommandUnknown(f"{command} is unknown. {message}")
            else:
                raise MessageCommandUnknown(
                    "No command sent with the message. {message}"
                )

        except Exception as exception:
            response_message = DataMessage(
                endpoints=message.endpoints.copy(),
                id=message.id,
                command=DataMessageCommands.EXCEPTION,
                properties={"exception": repr(exception)},
            )

        finally:
            if message.get("ack"):
                # If client requests acknowledgement and no other response has been created
                # then send response indicating task complete.
                if response_message is None:
                    response_message = DataMessage(
                        endpoints=message.endpoints.copy(),
                        id=message.id,
                        command=DataMessageCommands.COMPLETE,
                    )
                asyncio.create_task(message.send(self.signalling_port.get_socket()))

    @SignallingCommands.register(command=SignallingMessageCommands.GROUP_ADD)
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

    @SignallingCommands.register(command=SignallingMessageCommands.GROUP_DISCARD)
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

    @SignallingCommands.register(command=SignallingMessageCommands.FLUSH)
    def _flush_all(self, _: SignallingMessage) -> None:
        """Command handler for FLUSHXXX: Reset the server.

        Remove all groups, subscriptions and messages from the server

        Args:
            _ (SignallingMessage): Received message (not used)
        """
        # TODO: Need to flush all client client caches as well - Track endpoints when
        # receiving signalling message. Then send to known endpoints. Purge endpoints
        # if not receiving a messages. within time-out period.
        for channel_name, channel_queue in self.message_store.items():
            channel_queue.stop()
        self.message_store: Dict[bytes, ChannelQueue] = {}
        self.group_store: Dict[bytes, Dict[bytes, datetime]] = {}

    @SignallingCommands.register(command=SignallingMessageCommands.PRINT)
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
