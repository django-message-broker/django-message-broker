"""
Implements a message queue within the Django Message Broker server.

Includes:

*   Endpoint - A class containing zero message queue routing back to the subscriber's client.
*   RoundRobinDict - Implements a dictionary of messages over which the channel queue iterates,
    returning to the first item in the list when the end is reached.
*   ChannelQueue - Implements a channel queue within the server.

"""

from asyncio.locks import Event
from asyncio import CancelledError, create_task, sleep, wait, ALL_COMPLETED
from collections import UserDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, FrozenSet, Iterator, List, Optional, Union
import zmq
from zmq.eventloop.zmqstream import ZMQStream
from .utils import WeakPeriodicCallback

from .exceptions import (
    ChannelsSocketClosed,
    MessageFormatException,
    SubscriptionError,
    ChannelQueueFull,
)
from .data_message import DataMessage, DataMessageCommands
from .utils import IntegerSequence


@dataclass
class Endpoint:
    """Provides routing information for subscribers

    Attributes:
        socket (zmq.Socket, ZMQStream) : zmq.ROUTER socket or stream to which messages are sent.
        dealer (bytes) : Identity of zmq.DEALER to which messages are sent.
        is_process_channel(bool): The channel is a process channel (can have only one delivery endpoint).
        time_to_live (int): Number of seconds before the endpoint is discarded.
        expiry (Optional[datetime]) : Time when the endpoint will expire
    """

    socket: Union[zmq.Socket, ZMQStream]
    dealer: List = field(default_factory=lambda: [])
    subscriber_name: bytes = b""
    is_process_channel: bool = False
    time_to_live: Optional[int] = 86400
    expiry: Optional[datetime] = None

    @property
    def id(self) -> FrozenSet:
        """Returns a unique endpoint id from the routing information and channel name.

        Returns:
            FrozenSet: Unique endpoint id.
        """
        return frozenset(self.dealer + [self.subscriber_name])


class RoundRobinDict(UserDict):
    """Dictionary of endpoints that returns the next endpoint when a next value is requested
    and continues from the start of the list when the end of the list is reached.

    Notes:

    1.  Returns the value of the dictionary entry, not the key
    2.  StopIteration exception is not raised when the dictionary rolls over to the start.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.index = 0

    def __next__(self) -> Optional[Endpoint]:
        """Gets the next value of the next entry in the dictionary, returns to the first entry
        once the end of the dictionary is reached. Values are returned by insertion order.

        Returns:
            Optional[Endpoint]: Value of the next dictionary entry.
        """
        dict_len = len(self.data)
        return_value = None
        if dict_len:
            self.index = (self.index + 1) % len(self.data)
            return_value = self.data[list(self.data)[self.index]]
        return return_value

    def first_key(self) -> Optional[Any]:
        """Returns the first key in the dictionary by insertion order.

        Returns:
            Optional[int]: Value of the first key in the dictionary.
        """
        if self.data:
            return list(self.data)[0]
        else:
            return None


class ChannelQueue:
    """Provides a managed queue for storing and forwarding messages to endpoints. Messages
    are pulled from the queue and delivered to endpoints according to a round robin algorithm.
    The ordering of the round robin list is updated each time endpoints subscribe to the queue,
    with most recently updated channels going to the end of the list.

    Channel queues may be identified as Process Channels by the inclusion of an '!' within the channel
    name. These channels only have one endpoint. Attempts to change the endpoint (channel_name or
    dealer_id) or add additional endpoints result in a Subscription Exception.

    Once initialised, the queue starts an event loop which monitors the queue and sends messages in the
    queue once there are subscribers.

    Two additional callbacks are created, one to periodically scan unsent messages in the queue and
    remove those messages which are unsent after their expiry time. The second periodically scans
    subscribers and removes those who have passed their expiry time.

    Raises:
        SubscriptionError: Attempt to add multiple endpoints or change the endpoint of a Process Channel
    """

    def __init__(
        self, channel_name: bytes = b"", max_length: Optional[int] = None
    ) -> None:
        """Creates a new queue for the named channel.

        Args:
            channel_name (bytes, optional): Name of the channel. Defaults to b"".
            max_length (Optional[int]) : Maximum length of the queue.
        """
        self.channel_name = channel_name
        # Test channel name to establish whether this is a process specific channel
        try:
            _ = channel_name.decode("utf-8").index("!")
            self.is_process_channel = True
        except ValueError:
            self.is_process_channel = False

        self.max_length = max_length
        self.queue: Dict[int, DataMessage] = {}
        self.msq_sequence: Iterator = IntegerSequence().new_iterator()
        self.subscribers: RoundRobinDict = RoundRobinDict()
        self.subscribers_available: Event = Event()
        self.messages_available: Event = Event()

        self.flush_message_callback = WeakPeriodicCallback(
            self._flush_messages, callback_time=1000, jitter=0.1
        )
        self.flush_message_callback.start()
        self.flush_subscribers_callback = WeakPeriodicCallback(
            self._flush_subscribers, callback_time=5000, jitter=0.1
        )
        self.flush_subscribers_callback.start()

        self.task = create_task(self.event_loop())

    def stop(self):
        """Stop periodic callbacks and remove future tasks from the event queue. This
        should be called prior to deleting the object.
        """
        self.flush_message_callback.stop()
        self.flush_subscribers_callback.stop()
        self.task.cancel()

    def _set_subscribers_available(self) -> None:
        """Set (or clear) asyncio event if there are subscribers to the queue."""
        if self.subscribers:
            self.subscribers_available.set()
        else:
            self.subscribers_available.clear()

    def _set_messages_available(self) -> None:
        """Set (or clear) asyncio event if there are messages in the queue."""
        if self.queue:
            self.messages_available.set()
        else:
            self.messages_available.clear()

    def is_empty(self) -> bool:
        """Returns true if there are no subscribers and no messages.

        Returns:
            bool: True if the queue is empty and has no subscribers.
        """
        return not (self.subscribers or self.queue)

    async def event_loop(self) -> None:
        """Queue event loop. Waits for subscribers, and if there are message in the queue
        pull them from the queue and send them to the subscriber.
        """
        try:
            while True:
                await wait(
                    [self.subscribers_available.wait(), self.messages_available.wait()],
                    return_when=ALL_COMPLETED,
                )
                await self.pull_and_send()
        except CancelledError:
            pass

    def subscribe(self, endpoint: Endpoint) -> None:
        """Add subscribers to the channel. Subscribers are identified by the dealer that
        transmits the request. Multiple endpoints may be registered for normal channels
        (without the ! type indicator), only one endpoint may be registered for a process
        channel (indicated by the ! type indicator).

        Args:
            endpoint (Endpoint): Endpoint defining the receiver.

        Raises:
            SubscriptionError: Attempt to change or add multiple endpoints for a Process Channel
        """
        if endpoint.time_to_live:
            endpoint.expiry = datetime.now() + timedelta(seconds=endpoint.time_to_live)

        dealer: FrozenSet = endpoint.id
        if len(self.subscribers) == 0:
            self.subscribers[dealer] = endpoint
            if endpoint.is_process_channel:
                self.is_process_channel = True
        elif len(self.subscribers) == 1:
            if self.is_process_channel:
                if (
                    endpoint.is_process_channel
                    and dealer == self.subscribers.first_key()
                ):
                    self.subscribers[dealer] = endpoint
                else:
                    raise SubscriptionError(
                        "Unable to change endpoint of process channel."
                    )
            else:
                self.subscribers[dealer] = endpoint
        else:
            if endpoint.is_process_channel:
                raise SubscriptionError(
                    "Unable to change queue to process specific channel."
                )
            else:
                self.subscribers[dealer] = endpoint

        self._set_subscribers_available()

    def push(self, message: DataMessage, time_to_live: Optional[float] = 60):
        """Pushes a message onto the message queue.

        Args:
            message (DataMessage): Message to send to channel
            time_to_live (float): Number of seconds until message expires
        """
        if self.max_length and len(self.queue) >= self.max_length:
            raise ChannelQueueFull

        if time_to_live:
            message["expiry"] = datetime.now() + timedelta(seconds=time_to_live)
        self.queue[next(self.msq_sequence)] = message
        self._set_messages_available()

    async def pull_and_send(self) -> None:
        """Pulls a message from the queue and sends to an endpoints. Endpoints are chosen based
        upon a round-robin algorithm. If the mesage cannot be sent then it is add back to the
        end of the queue and the queue is penalised 100mSec to reduce rate of outbound messaging.
        """

        endpoint = None
        message: Optional[DataMessage] = None
        endpoint = next(self.subscribers)
        if endpoint:
            if self.queue:
                sequence = next(iter(self.queue))
                message = self.queue.pop(sequence)
                message.endpoints = endpoint.dealer
                message.channel_name = endpoint.subscriber_name
                message.command = DataMessageCommands.DELIVERY
                try:
                    await message.send(endpoint.socket)
                except ChannelsSocketClosed:
                    # If we cannot send then put message back on the queue after 100 mSecond penalty.
                    self.queue[sequence] = message
                    await sleep(0.1)
                except MessageFormatException:
                    # Silently drop incorrectly formatted messages.
                    pass

                self._set_messages_available()
                self._set_subscribers_available()

    def discard(self, endpoint: Endpoint):
        """Discards an endpoint from the queue.

        Args:
            endpoint (Endpoint): id of the dealer to discard.
        """
        dealer = endpoint.id
        try:
            del self.subscribers[dealer]
            self._set_subscribers_available()
        except KeyError:
            raise SubscriptionError(
                "Cannot unsubscribe, endpoint doesn't exist in the channel."
            )

    def _flush_messages(self) -> None:
        """Flush expired messsages from the queue."""
        for sequence in list(self.queue.keys()):
            try:
                expiry = self.queue[sequence]["expiry"]
                if expiry and datetime.now() > expiry:
                    del self.queue[sequence]
            except KeyError:
                pass
        self._set_messages_available()

    def _flush_subscribers(self) -> None:
        """Flush expired subscribers from the queue."""

        for sequence in list(self.subscribers.keys()):
            try:
                if datetime.now() > self.subscribers[sequence].expiry:
                    del self.subscribers[sequence]
            except KeyError:
                pass
        self._set_subscribers_available()
