"""
Implements a message queue, used within the client for the Django Message Broker.
"""
import asyncio
from asyncio.locks import Event
from datetime import datetime, timedelta
import sys
from typing import Dict, Iterator, Optional

from .utils import WeakPeriodicCallback
from .utils import IntegerSequence
from .utils import WaitFor
from .exceptions import ChannelFlushed
from .data_message import DataMessage


class ClientQueue:
    """Client message queue.

    When the client receives messages they are automatically appended to the channel queue by
    the receive data callback. Client functions are then able to wait on the queue until a
    message is available.
    """

    def __init__(
        self, channel_name: bytes = b"", time_to_live: Optional[float] = None
    ) -> None:
        """Creates a message queue for a given channel name.

        Args:
            channel_name (bytes, optional): Channel name. Defaults to b"".
        """
        self.channel_name = channel_name
        self.time_to_live: float = time_to_live or 86400
        self.expiry: datetime = datetime.now() + timedelta(seconds=self.time_to_live)

        self.queue: Dict[int, DataMessage] = {}
        self.messages_available: Event = asyncio.Event()
        self.terminating: Event = asyncio.Event()
        self.msq_sequence: Iterator = IntegerSequence().new_iterator()

        self.flush_message_callback = WeakPeriodicCallback(
            self._flush_messages, callback_time=1000, jitter=0.1
        )
        self.flush_message_callback.start()

    def stop(self):
        """Stop periodic callbacks and remove future tasks from the event queue. This
        should be called prior to deleting the object.
        """
        self.messages_available.clear()
        self.flush_message_callback.stop()
        self.terminating.set()

    def _set_messages_available(self) -> None:
        """Set (or clear) asyncio event if there are message in the queue."""
        self.set_expiry = datetime.now() + timedelta(seconds=self.time_to_live)
        if self.queue:
            self.messages_available.set()
        else:
            self.messages_available.clear()

    def push(self, message: DataMessage) -> None:
        """Pushes a message onto the key.

        The message may arrive with an expiry time already set, this time should not be modified.
        If an expiry time has not been set, and a time to live is defined, then the expiry time
        for the message is determined and appended to the message.

        Args:
            message (DataMessage): Data message.
        """
        # The time to live starts when the message arrives at the server, do not
        # reset the expiry time if it has already been set.
        if message.get("expiry") is None:
            try:
                time_to_live: float = message["ttl"]
                message["expiry"] = datetime.now() + timedelta(seconds=time_to_live)
            except KeyError:
                pass
        self.queue[next(self.msq_sequence)] = message
        self._set_messages_available()

    async def pull(self) -> Optional[DataMessage]:
        """Pull a message from the queue.

        Waits for a message to become available and then returns the first message
        received by the queue.

        If the queue is terminated without a message (because it has been flushed
        due to inactivity) then return None.

        Returns:
            Optional[DataMessage]: Data message
        """
        await WaitFor([self.messages_available, self.terminating]).one_event()
        if self.messages_available.is_set() and self.queue:
            sequence = next(iter(self.queue))
            message = self.queue.pop(sequence)
            self._set_messages_available()
        elif self.terminating.is_set():
            raise ChannelFlushed
        else:
            message = None

        return message

    @property
    def is_empty(self) -> bool:
        """Returns true if the queue is empty

        Returns:
            bool: Returns True if the queue is empty.
        """
        return len(self.queue) == 0

    @property
    def clients_waiting(self) -> bool:
        """Returns true if there are clients waiting to receive a message.

        Returns:
            bool: True if clients waiting for a message.
        """
        # Count of references to messages_available:
        # self + getrefcount + number of clients waiting to pull a message.
        return (sys.getrefcount(self.messages_available) - 2) > 0

    @property
    def can_be_flushed(self) -> bool:
        """True if the channel can be flushed from the message store.

        A channel can be flushed when there are no messages and no subscribers
        to the queue, and the expiry date has been passed.

        Returns:
            bool: True if the channel can be flushed.
        """
        return (
            self.is_empty
            and not self.clients_waiting
            and (datetime.now() > self.expiry)
        )

    def _flush_messages(self) -> None:
        """Remove expired messages from the queue.

        Periodic callback to remove expired messages from the queue.
        """
        for sequence in list(self.queue.keys()):
            try:
                expiry = self.queue[sequence].get("expiry")
                if expiry and datetime.now() > expiry:
                    del self.queue[sequence]
            except KeyError:
                pass
        self._set_messages_available()
