"""
Implements a data message as a structured dataclass. Used to pass data
messages between the Django Message Broker clients and server.
"""
from __future__ import annotations
from asyncio.futures import Future

from copy import deepcopy
from dataclasses import dataclass, field
from msgspec.core import encode, decode
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
from zmq.eventloop.zmqstream import ZMQStream
import zmq

from .exceptions import MessageFormatException, MessageTooLarge, ChannelsSocketClosed

DJANGO_CHANNELS_DATABASE_MAX_MESSAGE_SIZE = 1024000


@dataclass
class DataMessageCommands:
    """Valid message commands for data messages.

    **Client to server**:

    + SUBSCRIBE (b"SUBCHANX") - Subscribe to a channel.
    + UNSUBSCRIBE (b"USUBCHAN") - Unsubscribe from a channel.
    + SEND_TO_CHANNEL (b"SENDCHAN") - Send this message to a channel.
    + SEND_TO_GROUP (b"SENDGRPX") - Send this message to a group.

    **Server to client**:

    + DELIVERY (b"DELIVERY") - Deliver this message to a client.
    + COMPLETE (b"COMPLETE") - Command complete
    + EXCEPTION (b"EXCEPTON") - Command raised an exception.
    + SUBSCRIPTION_ERROR (b"ESUBCHAN") - Error subscribing to channel.

    **Both ways**:

    + KEEPALIVE (b"HARTBEAT") - Intermittent message confirming client/server alive.
    """

    SUBSCRIBE = b"SUBCHANX"
    UNSUBSCRIBE = b"USUBCHAN"
    SEND_TO_CHANNEL = b"SENDCHAN"
    SEND_TO_GROUP = b"SENDGRPX"
    DELIVERY = b"DELIVERY"
    SUBSCRIPTION_ERROR = b"ESUBCHAN"
    COMPLETE = b"COMPLETE"
    EXCEPTION = b"EXCEPTON"
    KEEPALIVE = b"HARTBEAT"


@dataclass
class DataMessage:
    """
    Message is formatted on wire as n + 1 + 6 frames. Where n is the number of routing_ids added to the front of a
    message on zmq.DEALER to zmq.ROUTER messages; 1 is the null frame to separate routing_ids from the message;
    and 6 is the number of frames in the message.

    + frame -1:-n: Routing IDs (list of zmq.DEALER identities)
    + frame 0: b"" blank frame
    + frame 1: channel_name - Name of channel or group to which message is sent
    + frame 2: command - Message type (publish to channel, to group, subscribe to channel)
    + frame 3: id - Unique universal identifier identifying messages in the same sequence of communication.
    + frame 4: sequence - Sequence number of this message from this publisher.
    + frame 5: properties - Properties appended to message
    + frame 6: body (serialisable object) - Body of message (as dictionary) Maximum size 1MB.
    """

    endpoints: List = field(default_factory=lambda: [])
    channel_name: bytes = b"Default"
    command: bytes = b"XXXXXXXX"
    id: bytes = field(default_factory=lambda: uuid4().bytes)
    sequence: int = 0
    properties: Dict = field(default_factory=lambda: {})
    encoded_body: Optional[bytes] = b"{}"
    body: Optional[Dict] = None

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

    def get_body(self) -> Dict:
        """Returns the value of the message, unpacking the message if the body
        is encoded.

        Note: The default is NOT to decode the body of the message when it is received. This
        reduces the number of times the body (which can be up to 1MB in size) is decoded/encoded
        when traversing servers and routers. Accessing the body of the message using the message
        attribute is potentially unsafe if the body of the message has not be decoded. Therefore,
        accessing the body should be using the get_body() method.

        Returns:
            Dict: Body of the message.
        """
        if not self.body:
            self.body = decode(self.encoded_body or b"{}")
        return self.body

    def __repr__(self) -> str:
        """Returns a printable string of data message contents.

        Returns:

        *   Endpoint list
        *   Channel name
        *   Unique message id
        *   Command
        *   Size of data body
        *   Properties
        *   Data body

        Returns:
            str: Data message contents.
        """
        if self.body is None and self.encoded_body:
            self.body = decode(self.encoded_body)
        if self.body is None:
            size = 0
            data = b"NULL"
        else:
            size = len(encode(self.body))
            data = repr(self.body)

        representation = "[endps:{ep}][chan:{channel}][id:{id}][cmd:{command}]\
            [size:{size}][props:{props}][data:{body}]".format(
            ep=self.endpoints,
            channel=self.channel_name,
            id=self.id,
            command=self.command,
            size=size,
            props=encode(self.properties),
            body=data,
        )

        return representation

    def quick_copy(self) -> DataMessage:
        """Returns a new instance of the message with all new envelope items and shared (between
        instances) body object. The purpose of providing a new envelope with shared body is to support
        copying the message for transmission to multiple addressees where the envelope must change but
        the body of the message does not. Sharing the body object reduces copying time, memory utilisation.

        Returns:
            DataMessage: Copy of the message with shared body object.
        """
        return DataMessage(
            endpoints=deepcopy(self.endpoints),
            channel_name=self.channel_name,
            command=self.command,
            id=self.id,
            sequence=self.sequence,
            properties=deepcopy(self.properties),
            encoded_body=self.encoded_body,
            body=self.body,
        )

    def copy(self) -> DataMessage:
        """Returns a new instance of the message deepcopying all objects. This returns an copy of the
        message which is independent of the original message.

        Returns:
            DataMessage: [description]
        """
        return DataMessage(
            endpoints=deepcopy(self.endpoints),
            channel_name=self.channel_name,
            command=self.command,
            id=self.id,
            sequence=self.sequence,
            properties=deepcopy(self.properties),
            encoded_body=deepcopy(self.encoded_body),
            body=deepcopy(self.body),
        )

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
            encoded_sequence = encode(self.sequence)
            encoded_properties = encode(self.properties)
            if self.body:
                encoded_body = encode(self.body)
                size = len(encoded_body)
                if size > DJANGO_CHANNELS_DATABASE_MAX_MESSAGE_SIZE:
                    raise MessageTooLarge("Message body is too large to send.")
            else:
                encoded_body = self.encoded_body

            message = [
                *self.endpoints,
                b"",
                self.channel_name,
                self.command,
                self.id,
                encoded_sequence,
                encoded_properties,
                encoded_body,
            ]
            socket.send_multipart(message)
        except Exception as e:
            if socket is None or socket.closed:
                raise ChannelsSocketClosed
            raise MessageFormatException(e)

    @classmethod
    def recv(cls, socket: zmq.Socket) -> DataMessage:
        """Reads  message from socket, returns new message instance."""
        return cls.from_msg(socket.recv_multipart())

    @classmethod
    def from_msg(
        cls, multipart_message: Union[Future, List], unpack_body=True
    ) -> DataMessage:
        """Returns a new message instance from zmq multipart message frames.

        The body of the message is decoded by default, though this can be over-ridden if the body
        does not need decoded. This may be advantageous where the message is being stored and forwarded to
        the final destination (e.g. in a server or router).

        Args:
            multipart_message (Union[Future, List]): A list (or list in a Future) of zmq multipart frames.
            unpack_body (bool, optional): Decode the body. Defaults to True.

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

        if len(message_frames) != 6:
            raise MessageFormatException("The message data message must be six frames.")
        (
            channel_name,
            command,
            id,
            packed_sequence,
            encoded_properties,
            encoded_body,
        ) = message_frames
        sequence = decode(packed_sequence)
        properties = decode(encoded_properties)
        if unpack_body:
            body = decode(encoded_body)
            encoded_body = b"{}"
        else:
            body = None
        return cls(
            endpoints=endpoints,
            channel_name=channel_name,
            command=command,
            id=id,
            sequence=sequence,
            properties=properties,
            encoded_body=encoded_body,
            body=body,
        )
