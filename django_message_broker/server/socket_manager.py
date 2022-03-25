"""
Wrapper around Zero Message Queue to manage sockets.
"""

from asyncio import Future
import ipaddress
from typing import Any, Callable, List, Optional, Union

from tornado.ioloop import IOLoop
from .exceptions import ChannelsServerError
import zmq

from zmq.eventloop.zmqstream import ZMQStream


class SocketManager:
    """Creates a zero-messsage-queue (ZMQ) socket."""

    def __init__(
        self,
        context: Optional[zmq.Context] = None,
        bind_ip_address: str = "127.0.0.1",
        port: int = 5555,
        is_server: bool = False,
        io_loop: IOLoop = None,
    ) -> None:
        """ZMQ Socket Manager

        Creates a zero message queue socket, establishes a zero message queue stream and permits a callback
        to be added which is called when a message is received.

        Args:
            context (zmq.Context, optional):    Context for the zmq installation.
                                                Defaults to zmq.Context().
            bind_ip_address (str, optional):    IP address to which the socket is bound/connected.
                                                Both IPv4 and IPv6 addresses are supported.
                                                Defaults to "127.0.0.1".
            port (int, optional):               Port to which the socket is bound connected. Defaults to 5555.
            is_server (bool, optional):         Is this a server socket (zmq.ROUTER).
                                                Defaults to False (zmq.DEALER).
            io_loop (IOLoop, optional):         Tornado Event loop used to support callbacks.
                                                Defaults to current Tornado event loop.

        Raises:
            ChannelsServerError: Error raised if the socket cannot be created.
        """
        self._ipv6 = False
        if bind_ip_address == "*":
            self._ip_address = "*"
        else:
            try:
                valid_ip_address = ipaddress.ip_address(bind_ip_address)
                self._ip_address = str(valid_ip_address)
                if valid_ip_address == 6:
                    self._ipv6 = True
            except ValueError as e:
                raise ChannelsServerError(e)

        self._context: zmq.Context = context or zmq.Context()
        self._port = port
        self._is_server = is_server
        self.io_loop = io_loop if io_loop else IOLoop.current()
        self.type = zmq.ROUTER if is_server else zmq.DEALER

        self.socket: Optional[zmq.Socket] = None
        self.stream: Optional[ZMQStream] = None

        self.receive_callback: Optional[Callable[[List[Any]], None]] = None

    def get_socket(self) -> zmq.Socket:
        """Get the ZMQ socket.

        Raises:
            ChannelsServerError: Raises error if there is no socket.

        Returns:
            zmq.Socket: ZMQ socket.
        """
        if not self.socket:
            raise ChannelsServerError
        return self.socket

    def get_stream(self) -> ZMQStream:
        """Get the ZMQ stream.

        Raises:
            ChannelsServerError: Raises error if there is no stream.

        Returns:
            ZMQStream: ZMQ stream.
        """
        if not self.stream:
            raise ChannelsServerError
        return self.stream

    def get_routing_id(self) -> Optional[bytes]:
        """Returns the routing ID if the sockets is a ZMQ.Dealer (client socket).

        Returns:
            Optional[bytes]: Routing ID of the socket.
        """
        routing_id: Optional[bytes] = None
        if self.socket and self.type == zmq.DEALER:
            routing_id = self.socket.getsockopt(zmq.ROUTING_ID)
        return routing_id

    def start(self) -> None:
        """Opens the socket, sets up streams and configures callbacks."""
        if self.socket is None or self.socket.closed:
            self.socket = self._context.socket(self.type)
            if self._is_server:
                self.socket.bind(f"tcp://{self._ip_address}:{self._port}")
            else:
                self.socket.connect(f"tcp://{self._ip_address}:{self._port}")
            if self._ipv6:
                self.socket.setsockopt(zmq.IPV6, 1)
            # Linger after socket close to ensure messages are sent (mSec)
            self.socket.setsockopt(zmq.LINGER, 1000)
            # Limit messages in queue. Note this is per client.
            # Max memory is #clients x #messages(100) x #message-size(1MB) => approx 100MB per client.
            # When high water mark is reached, socket will drop outbound messages.
            self.socket.setsockopt(zmq.SNDHWM, 100)
            self.stream = ZMQStream(self.socket, io_loop=self.io_loop)

        # Establish/ re-establish an receive callbacks.
        if self.receive_callback and self.stream:
            self.stream.on_recv(self.receive_callback)

    def stop(self) -> None:
        """Closes the socket, streams and clears configured callbacks."""
        if self.stream:
            self.stream.stop_on_recv()
            self.stream.close()
        if self.socket and not self.socket.closed:
            self.socket.close()
            if self._is_server:
                self.socket.unbind(f"tcp://{self._ip_address}:{self._port}")
            else:
                self.socket.disconnect(f"tcp://{self._ip_address}:{self._port}")

    def set_receive_callback(
        self, callback: Callable[[Union[Future, List[Any]]], None]
    ) -> None:
        """Sets the callback when a message is received on the socket.

        Args:
            callback (Callable[[Union[Future, List[Any]]], None]): Callback method accepting Future or List

        Note: The callback needs to accept a multipart_message which could be either of the following types:

        + List: Multi-part message with each frame expressed as an element in the list.
        + asyncio Future: An asyncio Future containing the above list.

        The callback function should test whether the returned multipart message is a Future and then
        extract the multipart list as follow:

        .. highlight:: python
        .. code-block:: python

            from asyncio.futures import Future

            def callback(multipart_message: Union[Future, List]):
                if isinstance(multipart_message, Future):
                    multipart_list = multipart_message.result()
                else:
                    multipart_list = multipart_message
        """
        # cache the callback so that it can be setup when the socket starts
        self.receive_callback = callback
        if self.stream:
            self.stream.on_recv(callback)

    def clear_receive_callback(self) -> None:
        """Clear the callback that is called when a message is received."""
        self.receive_callback = None
        if self.stream:
            self.stream.stop_on_recv()
