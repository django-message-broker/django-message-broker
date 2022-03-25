"""
Implements a signalling message as a structured dataclass. Used to pass signaling
message between the Django Message Broker clients and server.
"""

from __future__ import annotations
from asyncio.futures import Future

from dataclasses import dataclass, field
from msgspec.core import encode, decode
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
from zmq.eventloop.zmqstream import ZMQStream
import zmq

from .exceptions import MessageFormatException


@dataclass
class SignallingMessageCommands:
    """Valid message commands for signalling messages.

    **Client to server**

    + GROUP_ADD (b"GROUPADD") - Add a channel to a group.
    + GROUP_DISCARD (b"GROUPDIS") - Remove a channel from a group.
    + FLUSH (b"FLUSHXXX") - Remove all groups, subscriptions and messages from the server.
    + PRINT (b"PRINTXXX") - Print contents of message store and group store to terminal.
    + PERFORMANCE (b"PERFMNCE") - Request performance report


    **Server to client**

    + COMPLETE (b"COMPLETE") - Command complete
    + EXCEPTION (b"EXCEPTON") - Command raised an exception.
    + PERFORMANCE_REPORT (b"PERFRPRT") - Transmit performance report
    + FLUSH_CLIENT (b"FLUSHCXX") - Flush client message store.

    **Both ways**

    + KEEPALIVE (b"HARTBEAT") - Intermittent message confirming client/server alive.
    """

    GROUP_ADD = b"GROUPADD"
    GROUP_DISCARD = b"GROUPDIS"
    FLUSH = b"FLUSHXXX"
    FLUSH_CLIENT = b"FLUSHCXX"
    PRINT = b"PRINTXXX"
    PERFORMANCE = b"PERFMNCE"
    PERFORMANCE_REPORT = b"PERFRPRT"
    COMPLETE = b"COMPLETE"
    EXCEPTION = b"EXCEPTON"
    KEEPALIVE = b"HARTBEAT"


@dataclass
class SignallingMessage:
    """
    Message is formatted on wire as n + 1 + 3 frames. Where n is the number of routing_ids added to the front of a
    message on zmq.DEALER to zmq.ROUTER messages; 1 is the null frame to separate routing_ids from the message;
    and 3 is the number of frames in the message.

    + frame -1:-n: Routing IDs (list of zmq.DEALER identities)
    + frame 0: b"" blank frame
    + frame 1: id - Unique universal identifier for tracking commands
    + frame 2: command - Message type (publish to channel, to group, subscribe to channel)
    + frame 3: properties - Properties appended to message
    """

    endpoints: List = field(default_factory=lambda: [])
    id: bytes = field(default_factory=lambda: uuid4().bytes)
    command: bytes = b"XXXXXXXX"
    properties: Dict = field(default_factory=lambda: {})

    def __getitem__(self, key: Union[int, str]) -> Any:
        """Returns values stored in the properties frame of the message.

        Args:
            key (Union[int, str]): Property key

        Returns:
            Optional[Any]: Value stored in the property.

        Raises:
            KeyError: If the key doesn't exist.
        """
        return self.properties[key]

    def get(self, key: Union[int, str], default: Optional[Any] = None) -> Optional[Any]:
        """Returns values stored in the properties frame of the message.

        Args:
            key (Union[int, str]): Property key.
            default (Any, optional): Default value if key doesn't exist.

        Returns:
            Optional[Any]: Property value if key exists, default or None if it doesn't.
        """
        return self.properties.get(key, default)

    def __setitem__(self, key: Union[int, str], value: Any) -> None:
        """Sets the value of a property in the properties frame of the message.

        Args:
            key (Union[int, str]): Property key
            value (Any): Value of the property (must be serialisable by msgspec)
        """
        self.properties[key] = value

    def __repr__(self) -> str:
        """Returns a printable string of signalling message contents.

        Returns:

        *   Endpoint list
        *   Unique message id
        *   Command
        *   Properties

        Returns:
            str: Signalling message contents.
        """
        representation = "[endps:{ep}][seq:{id}][cmd:{command}][props:{props}]".format(
            ep=self.endpoints, id=self.id, command=self.command, props=self.properties
        )
        return representation

    async def send(self, socket: Union[zmq.Socket, ZMQStream]) -> None:
        """Sends a message on the defined socket or stream.

        Args:
            socket (Union[zmq.Socket, ZMQStream]): Socket or stream on which message sent.

        Raises:
            MessageTooLarge: The body of the message exceeds the maximum permissible.
            ChannelsSocketClosed: Socket or stream closed.
            MessageFormatException: Error occurred sending the message.
        """
        try:
            encoded_properties = encode(self.properties)
            message = [
                *self.endpoints,
                b"",
                self.id,
                self.command,
                encoded_properties,
            ]
        except TypeError as exception:
            message = [
                *self.endpoints,
                b"",
                self.id,
                SignallingMessageCommands.EXCEPTION,
                encode({"exception": repr(exception)}),
            ]
        socket.send_multipart(message)

    @classmethod
    def recv(cls, socket: zmq.Socket) -> SignallingMessage:
        """Reads  message from socket, returns new message instance."""
        return cls.from_msg(socket.recv_multipart())

    @classmethod
    def from_msg(cls, multipart_message: Union[Future, List]) -> SignallingMessage:
        """Returns a new message instance from zmq multipart message frames.

         Args:
            multipart_message (Union[Future, List]): A list (or list in a Future) of zmq multipart frames.

        Raises:
            MessageFormatException: If the number of frames in the multipart message doesn't match the schema.

        Returns:
            DataMessage: New instance of the message.
        """
        # If Asyncio has returned a list wrapped in a Future extract resulting list.
        if isinstance(multipart_message, Future):
            multipart_list = multipart_message.result()
        else:
            multipart_list = multipart_message
        null_record_index = [
            index for index, frame in enumerate(multipart_list) if frame == b""
        ][0]
        endpoints = multipart_list[:null_record_index]
        message_frames = multipart_list[null_record_index + 1 :]

        if len(message_frames) != 3:
            raise MessageFormatException("The signalling message must be three frames.")
        id, command, encoded_properties = message_frames
        properties = decode(encoded_properties)
        return cls(
            endpoints=endpoints,
            id=id,
            command=command,
            properties=properties,
        )
