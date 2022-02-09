class MessageFormatException(Exception):
    """The message format is incorrect."""


class MessageCommandUnknown(Exception):
    """The command in the received message is unknown."""


class MessageTooLarge(Exception):
    """The messsage is too large."""


class SubscriptionError(Exception):
    """Error whilst subscribing to channel"""


class ChannelsServerError(Exception):
    """General server exception."""


class ChannelQueueFull(Exception):
    """Channel queue is full."""


class ChannelsSocketClosed(Exception):
    """Exception raised when message pushed to closed socket."""
