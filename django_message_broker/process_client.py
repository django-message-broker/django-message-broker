"""
Implements a client for the Django Message Broker within a process
"""
from typing import Dict, Union
from .server.channels_client import ChannelsClient
import random
import string


class ProcessClient(ChannelsClient):
    """Implements a process client."""

    def __init__(
        self, expiry=60, group_expiry=86400, ip_address="127.0.0.1", port=5556, **kwargs
    ):
        super().__init__(ip_address=ip_address, port=port, **kwargs)
        self.expiry = expiry
        self.group_expiry = group_expiry

    def _coerce_bytes(self, value: Union[str, bytes]) -> bytes:
        """Coerce input of string or bytes to bytes.

        Args:
            value (Union[str, bytes]): Input value of either string or bytes

        Returns:
            bytes: Value coerced to bytes
        """
        return value.encode("utf-8") if isinstance(value, str) else value

    async def new_channel(self, prefix: str = "specific") -> str:
        """Returns a new channel name that can be used by something in our
        process as a specific channel.

        Args:
            prefix (str, optional): Prefix to channel name. Defaults to "specific".

        Returns:
            str: Process specific channel name.
        """
        channels_client_id = self._get_routing_id()
        random_id = "".join(random.choice(string.ascii_letters) for i in range(12))
        new_process_channel_name = f"{prefix}.{channels_client_id}!{random_id}"

        return new_process_channel_name

    async def send(self, channel: str, message: Dict) -> None:
        """Send a message onto a (general or specific) channel.

        Args:
            channel (str): Channel name
            message (Dict): Message to send
        """
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
        channel_name = self._coerce_bytes(channel)
        subscriber_name = channel_name
        await self._subscribe(channel_name, subscriber_name)
        message = await self._receive(subscriber_name)
        return message

    async def group_add(self, group: str, channel: str) -> None:
        """Adds the channel to a group. If the group doesn't exist then it is created.
        A subscription request is also sent to the server to ensure that messages are
        delivered locally.

        Args:
            group (str): Name of the group to join.
            channel (str): Channel joining the group.
        """
        channel_name = self._coerce_bytes(channel)
        group_name = self._coerce_bytes(group)
        await self._group_add(group_name, channel_name)

    async def group_discard(self, group: str, channel: str) -> None:
        """Removes a channel from a group

        Args:
            group (str): Group name
            channel (str): Channel name
        """
        channel_name = self._coerce_bytes(channel)
        group_name = self._coerce_bytes(group)
        await self._group_discard(group_name, channel_name)

    async def group_send(self, group: str, message: dict) -> None:
        """Sends a message to a group

        Args:
            group (str): Group name
            message (str): Message
        """
        group_name = self._coerce_bytes(group)
        await self._send_to_group(group_name, message, time_to_live=self.expiry)
