from asyncio.futures import Future
from asyncio.locks import Event
from datetime import datetime
import uuid
from tornado.ioloop import IOLoop, PeriodicCallback
from typing import Dict, List, Union
from zmq.asyncio import Context

from .client_queue import ClientQueue
from .data_message import DataMessage, DataMessageCommands
from .exceptions import (
    ChannelsServerError,
    MessageCommandUnknown,
)
from .signalling_message import SignallingMessage, SignallingMessageCommands
from .socket_manager import SocketManager
from .utils import MethodRegistry


class ChannelsClient:
    """Client for Django Channels message server.

    Implements a client to the network message server for Django channels using
    zero message queue (ZMQ) to support communication between channels registered
    within different processes.

    The server opens two sequential ports:

    + Data port (base port, default=5556): Transmission of data messages between the client and server.

    + Signalling port (base port + 1, default=5557): Transmission of signalling messages between the client and server.
    """
    class DataCommands(MethodRegistry):
        """Create registry of data commands using decorator."""
        pass

    class SignallingCommands(MethodRegistry):
        """Create registry of signalling commands using decorator."""
        pass

    def __init__(
        self, *args, ip_address: str = "127.0.0.1", port: int = 5556, **kwargs,
    ):
        """Client to the message server for Django Channels.

        Args:
            ip_address (str, optional): IP address to which sockets connect. Defaults to "127.0.0.1".
            port (int, optional): Base port for the server. Defaults to 5556.

        Raises:
            ChannelsServerError: Raised when an error occurs in the client.
        """
        super().__init__(*args, **kwargs)

        self.message_store: Dict[bytes, ClientQueue] = {}
        self.group_store: Dict[bytes, Dict[bytes, datetime]] = {}
        self.channel_time_to_live = 86400

        # Create jump dictionaries to index callable methods on message commands.
        self.data_callables = ChannelsClient.DataCommands.get_bound_callables(self)
        self.signalling_callables = ChannelsClient.SignallingCommands.get_bound_callables(self)

        self.ip_address = ip_address
        self.port = port

        # Dictionary to containing locks awaiting confirmation that a message
        # was processed by server.
        self.data_response_event: Dict[bytes, Event] = {}
        self.signalling_response_event: Dict[bytes, Event] = {}

        # Setup the zmq context, event loop and sockets.
        # Note: the client uses the asyncio context.
        self.ctx = Context.instance()
        self.core_event_loop = IOLoop.current()

        try:
            self.data_manager = SocketManager(
                self.ctx,
                self.ip_address,
                self.port,
                is_server=False,
                io_loop=self.core_event_loop,
            )
            self.data_manager.set_receive_callback(self._receive_data)
        except ChannelsServerError:
            raise ChannelsServerError("Unable to create client data socket")

        try:
            self.signalling_manager = SocketManager(
                self.ctx,
                self.ip_address,
                self.port + 1,
                is_server=False,
                io_loop=self.core_event_loop,
            )
            self.signalling_manager.set_receive_callback(self._receive_signalling)
        except ChannelsServerError:
            raise ChannelsServerError("Unable to create client signalling socket")

        # Establish callbacks to flush stale queues and groups.
        self.flush_queues_callback = PeriodicCallback(
            self._flush_queues, callback_time=1000, jitter=0.1
        )

        # Open sockets
        self.data_manager.start()
        self.signalling_manager.start()
        self.flush_queues_callback.start()

    def stop(self):
        self.data_manager.stop()
        self.signalling_manager.stop()
        self.flush_queues_callback.stop()

    def _flush_queues(self) -> None:
        """Periodic callback to flush queues where there are no subscribers or messages."""
        queues = list(self.message_store.keys())
        for queue in queues:
            if self.message_store[queue].can_be_flushed:
                del self.message_store[queue]

    async def _await_data_response(self, message_id: bytes) -> None:
        """Creates an event which is set when a confirmation message is received on the
        data channel from the server.

        Args:
            message_id (bytes): Message id of the sent message for which a response is required.
        """
        self.data_response_event[message_id] = Event()
        await self.data_response_event[message_id].wait()

    async def _await_signalling_response(self, message_id: bytes) -> None:
        """Creates an event which is set when a confirmation message is received on the
        signalling channel from the server.

        Args:
            message_id (bytes): Message id of the sent message for which a response is required.
        """
        self.signalling_response_event[message_id] = Event()
        await self.signalling_response_event[message_id].wait()

    def _get_routing_id(self) -> str:
        """Returns the routing id from the zmq.DEALER socket used to route message from
        the server to the client. The routing id is a 32-bit unsigned integer which is
        appended to the string `zmq_id_` to provide a unique channels client identifier.

        Returns:
            str: Routing id
        """
        id_b = self.data_manager.get_routing_id()
        routing_id = int.from_bytes(id_b, byteorder="big", signed=False) if id_b else 0
        channels_id = f"zmq_id_{routing_id}"
        return channels_id

    def _get_subscriber_id(self) -> bytes:
        return f"sub_id_{uuid.uuid4().hex}".encode("utf-8")

    async def _receive(self, subscriber_name: bytes) -> Dict:
        """Receive the first message that arrives on the channel.
        If more than one coroutine waits on the same channel, a random one
        of the waiting coroutines will get the result.

        Args:
            channel (bytes): Channel name

        Returns:
            Dict: Received message.
        """
        if self.message_store.get(subscriber_name) is None:
            self.message_store[subscriber_name] = ClientQueue(channel_name=subscriber_name, time_to_live=self.channel_time_to_live)
        message = None
        while message is None:
            message = await self.message_store[subscriber_name].pull()

        return message.get_body()

    # Add unsubscribe
    async def _subscribe(self, channel_name: bytes, subscriber_name: bytes) -> None:
        """Subscribes to a channel to ensure that messages are delivered to the client.

        Args:
            channel_name (bytes): Name of channel subscribed to.
        """
        if self.message_store.get(subscriber_name) is None:
            self.message_store[subscriber_name] = ClientQueue(channel_name=subscriber_name, time_to_live=self.channel_time_to_live)

        subscribe_message = DataMessage(
            command=DataMessageCommands.SUBSCRIBE,
            channel_name=channel_name,
            properties={"subscriber_name": subscriber_name},
        )
        await subscribe_message.send(self.data_manager.get_socket())

    async def _send(
        self, channel_name: bytes, message: Dict, time_to_live: float = 60, acknowledge=False
    ) -> None:
        """Sends a message to a channel.

        Args:
            channel (Union[str, bytes]): Channel name
            message (Dict): Message to send (as a dictionary)
            time_to_live (float, optional): Time to live (seconds). Defaults to 60.
        """
        # TODO: Send with acknowledgement.
        data_message = DataMessage(
            channel_name=channel_name,
            command=DataMessageCommands.SEND_TO_CHANNEL,
            properties={
                "ttl": time_to_live,
                "ack": acknowledge
            },
            body=message,
        )
        await data_message.send(self.data_manager.get_socket())
        if acknowledge:
            # TODO: If acknowledge await response
            pass

    # TODO: Add pull a message from a channel (for cases where we do not want to store it locally)
    async def _pull(self, channel_name: bytes) -> None:
        """Waits for messages on the channel then pulls the first available."""
        pass

    async def _send_to_group(
        self, group_name: bytes, message: Dict, time_to_live: float = 60
    ) -> None:
        """Sends a message to a group.

        Args:
            group (Union[str, bytes]): Group name
            message (Dict): Message to send (as dictionary)
            time_to_live (int, optional): Time to live (seconds). Defaults to 60.
        """
        data_message = DataMessage(
            channel_name=group_name,
            command=DataMessageCommands.SEND_TO_GROUP,
            properties={"ttl": time_to_live},
            body=message,
        )
        await data_message.send(self.data_manager.get_socket())

    async def _group_add(self, group_name: bytes, channel_name: bytes):
        """Adds the channel to a group. If the group doesn't exist then it is created.
        A subscription request is also sent to the server to ensure that messages are
        delivered locally.

        Args:
            group (bytes): Name of the group to join.
            channel (bytes): Channel joining the group.
        """
        # Add channel to group
        add_group_message = SignallingMessage(
            command=SignallingMessageCommands.GROUP_ADD,
            properties={"group_name": group_name, "channel_name": channel_name},
        )
        await add_group_message.send(self.signalling_manager.get_socket())
        await self._await_signalling_response(add_group_message.id)

    async def _group_discard(self, group_name: bytes, channel_name: bytes) -> None:
        """Removes a channel from a group

        Args:
            group (bytes): Group name
            channel (bytes): Channel name
        """
        discard_group_message = SignallingMessage(
            command=SignallingMessageCommands.GROUP_DISCARD,
            properties={"group_name": group_name, "channel_name": channel_name},
        )
        await discard_group_message.send(self.signalling_manager.get_socket())
        await self._await_signalling_response(discard_group_message.id)

    def _receive_data(self, multipart_message: Union[Future, List]) -> None:
        """Callback that receives data messages from the server and dispatches
        them to the relevant handler method.

        Args:
            multipart_message (Union[Future, List]): zmq multipart message

        Raises:
            ImportError: Error raised if the multitpart message cannot be parsed to a valid data message.
            MessageCommandUnknown: The command in the message is unknown.
        """

        try:
            message = DataMessage.from_msg(multipart_message)
        except Exception as exception:
            raise ImportError(exception)

        command = message.command
        if command:
            call_function = self.data_callables.get(command)
            if call_function:
                call_function(message)
            else:
                raise MessageCommandUnknown(f"{command} is unknown. {message}")
        else:
            MessageCommandUnknown("No command sent with the message. {message}")

    @DataCommands.register(command=DataMessageCommands.DELIVERY)
    def _delivery(self, message: DataMessage) -> None:
        """Receive a message for delivery to subscribers of a channel and pushes it onto
        a message queue for later collection by the client method.

        Args:
            message (DataMessage): Data message.
        """
        subscriber_name = message.channel_name
        channel_queue = self.message_store.get(subscriber_name)
        if channel_queue is None:
            channel_queue = ClientQueue(channel_name=subscriber_name, time_to_live=self.channel_time_to_live)
            self.message_store[subscriber_name] = channel_queue
        channel_queue.push(message)

    @DataCommands.register(command=DataMessageCommands.SUBSCRIPTION_ERROR)
    def _subscription_error(self, message: DataMessage) -> None:
        """Attempt to subscribe to a channel failed.

        This method does not implement any actions. Potential implementations for this command are:

        1.  Raise an exception in the client.
        2.  Identify where the subscription request originated (based upon message id) and then raise
            an exception in the relevant receiving method.

        Args:
            message (DataMessage): Data message.
        """
        pass

    def _receive_signalling(self, multipart_message: Union[Future, List]) -> None:
        """Callback that receives signalling messages from the server and dispatches
        them to the relevant handler method.

        Args:
            multipart_message (Union[Future, List]): zmq multipart message

        Raises:
            ImportError: Error raised if the multitpart message cannot be parsed to a valid data message.
            MessageCommandUnknown: The command in the message is unknown.
        """
        try:
            message = SignallingMessage.from_msg(multipart_message)
        except Exception as exception:
            raise ImportError(exception)

        if message:
            command = message.command
            if command:
                call_function = self.signalling_callables.get(command)
                if call_function:
                    call_function(message)
                else:
                    raise MessageCommandUnknown(f"{command} is unknown. {message}")
            else:
                raise MessageCommandUnknown(
                    "No command sent with the message. {message}"
                )

    @SignallingCommands.register(command=SignallingMessageCommands.COMPLETE)
    def _signalling_task_complete(self, message: SignallingMessage) -> None:
        """Response from server indicating that the signalling command completed successfully.

        Called when a signalling message confirms that actions have completed. This then sets
        an event to release the signalling send thread to execute subsequent instructions.

        Args:
            message (SignallingMessage): Signalling message
        """
        event = self.signalling_response_event.get(message.id, None)
        if event:
            event.set()

    @SignallingCommands.register(command=SignallingMessageCommands.EXCEPTION)
    def _signalling_exception(self, message: SignallingMessage) -> None:
        """Response from server indicating that the signalling command generated a caught exception.

        This method does not implement any actions. Potential implementations for this command are:

        1.  Raise an exception in the client.
        2.  Identify where the subscription request originated (based upon message id) and then raise
            an exception in the relevant receiving method.

        Args:
            message (SignallingMessage): Signalling message
        """
        pass

    def _flush_messages(self, message: SignallingMessage) -> None:
        """Response from server indicating that the client should flush message which have not
        yet been received.

        This method does not implement any actions. It is intended that when a client sends a
        flush all message to the server, the server will send a flush messages command to all
        clients to remove any undelivered messages from the clients.

        Args:
            message (SignallingMessage): Signalling message
        """
        pass

    async def _flush_all(self):
        """Resets the server by flushing all messages from the message store, and
        groups from the group store.
        """
        flush_message = SignallingMessage(command=SignallingMessageCommands.FLUSH)
        await flush_message.send(self.signalling_manager.get_socket())
