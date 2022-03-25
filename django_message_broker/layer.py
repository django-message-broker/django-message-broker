"""
Channels installable channel backend using Django Message Broker
"""

from typing import Any, Dict, List, Union
import uuid

from .server.channels_client import ChannelsClient
from .base_channel_layer import BaseChannelLayer


class ChannelsServerLayer(ChannelsClient, BaseChannelLayer):
    """
    Django Message Broker channel layer backend.
    """

    def __init__(
        self,
        expiry=60,
        group_expiry=86400,
        capacity=100,
        channel_capacity=None,
        ip_address="127.0.0.1",
        port=5556,
        **kwargs,
    ):
        # Initialises ChannelsClient which then calls BaseChannelLayer
        super().__init__(
            expiry=expiry,
            # group_expiry=group_expiry,
            capacity=capacity,
            channel_capacity=channel_capacity,
            ip_address=ip_address,
            port=port,
            **kwargs,
        )

    @property
    def channels(self) -> List[bytes]:
        """Return list of channel names.

        Returns:
            List[bytes]: List of channel names.
        """
        return list(self.message_store)

    def _coerce_bytes(self, value: Union[str, bytes]) -> bytes:
        """Coerce input of string or bytes to bytes.

        Args:
            value (Union[str, bytes]): Input value of either string or bytes

        Returns:
            bytes: Value coerced to bytes
        """
        return value.encode("utf-8") if isinstance(value, str) else value

    # Channel layer API

    extensions = ["groups", "flush"]

    async def new_channel(self, prefix: str = "specific") -> str:
        """Returns a new channel name that can be used by something in our
        process as a specific channel.

        Args:
            prefix (str, optional): Prefix to channel name. Defaults to "specific".

        Returns:
            str: Process specific channel name.
        """
        channels_client_id = self.get_routing_id()
        random_id = uuid.uuid4().hex
        new_process_channel_name = f"{prefix}.{channels_client_id}!{random_id}"

        return new_process_channel_name

    async def send(self, channel: str, message: Dict) -> None:
        """Send a message onto a (general or specific) channel.

        Args:
            channel (str): Channel name
            message (Dict): Message to send
        """
        # TODO: Need to add check for capacity -> however, need to determine what would
        # be effective as the limitation is receive capacity not send. Though could limit number
        # of channels.
        # Typecheck
        assert isinstance(message, dict), "message is not a dict"
        assert self.valid_channel_name(channel), "Channel name not valid"
        assert "__asgi_channel__" not in message

        channel_name = self._coerce_bytes(channel)
        time_to_live = self.expiry
        await self._send(channel_name, message, time_to_live=time_to_live)

    async def receive(self, channel: str) -> Dict:
        """Receive the first message that arrives on the channel.
        If more than one coroutine waits on the same channel, a random one
        of the waiting coroutines will get the result. Subscribe to the channel
        first to ensure that the Channels client receive messages from the server.

        Args:
            channel (str): Channel name

        Returns:
            Dict: Received message.
        """
        assert self.valid_channel_name(channel)

        channel_name = self._coerce_bytes(channel)
        subscriber_name = channel_name
        await self._subscribe(channel_name, subscriber_name)
        message = await self._receive(subscriber_name)
        return message

    async def flush(self) -> None:
        """Resets the server by flushing all messages from the message store, and
        groups from the group store.
        """
        await self._flush_all()

    async def close(self) -> None:
        """Closes the client connection.

        It's not clear what the purpose of this function should be? Perhaps
        it is intended to trigger removal of channel from messages store?
        But would only make sense if process specific.
        """
        pass

    def _remove_from_groups(self, channel: str) -> None:
        """Removes a channel from all groups. Used when a message on it expires.

        NOT IMPLEMENTED

        Args:
            channel ([type]): Channel name
        """
        pass

    async def group_add(self, group: str, channel: str) -> None:
        """Adds the channel to a group. If the group doesn't exist then it is created.
        A subscription request is also sent to the server to ensure that messages are
        delivered locally.

        Args:
            group (str): Name of the group to join.
            channel (str): Channel joining the group.
        """
        assert self.valid_group_name(group), "Group name not valid"
        assert self.valid_channel_name(channel), "Channel name not valid"

        channel_name = self._coerce_bytes(channel)
        group_name = self._coerce_bytes(group)

        await self._group_add(group_name, channel_name)

    async def group_discard(self, group: str, channel: str) -> None:
        """Removes a channel from a group

        Args:
            group (str): Group name
            channel (str): Channel name
        """
        assert self.valid_channel_name(channel), "Invalid channel name"
        assert self.valid_group_name(group), "Invalid group name"

        channel_name = self._coerce_bytes(channel)
        group_name = self._coerce_bytes(group)

        await self._group_discard(group_name, channel_name)

    async def group_send(self, group: str, message: Dict[str, Any]) -> None:
        """Sends a message to a group

        Args:
            group (str): Group name
            message (str): Message
        """
        assert isinstance(message, dict), "Message is not a dict"
        assert self.valid_group_name(group), "Invalid group name"

        group_name = self._coerce_bytes(group)
        await self._send_to_group(group_name, message, time_to_live=self.expiry)
