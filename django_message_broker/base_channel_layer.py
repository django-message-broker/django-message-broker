"""
Copied from Django Channels memory layer.
"""
import fnmatch
import re


class BaseChannelLayer:
    """
    Base channel layer class that others can inherit from, with useful
    common functionality.
    """

    def __init__(self, expiry=60, capacity=100, channel_capacity=None):
        self.expiry = expiry
        self.capacity = capacity
        self.channel_capacity = channel_capacity or {}

    def compile_capacities(self, channel_capacity):
        """
        Takes an input channel_capacity dict and returns the compiled list
        of regexes that get_capacity will look for as self.channel_capacity
        """
        result = []
        for pattern, value in channel_capacity.items():
            # If they passed in a precompiled regex, leave it, else interpret
            # it as a glob.
            if hasattr(pattern, "match"):
                result.append((pattern, value))
            else:
                result.append((re.compile(fnmatch.translate(pattern)), value))
        return result

    def get_capacity(self, channel):
        """
        Gets the correct capacity for the given channel; either the default,
        or a matching result from channel_capacity. Returns the first matching
        result; if you want to control the order of matches, use an ordered dict
        as input.
        """
        for pattern, capacity in self.channel_capacity:
            if pattern.match(channel):
                return capacity
        return self.capacity

    def match_type_and_length(self, name):
        """Confirm object is a string and less than 100 characters.

        Args:
            name (Any): Object to test.

        Returns:
            bool : True if string less than 100 characters, else False.
        """
        if isinstance(name, str) and (len(name) < 100):
            return True
        return False

    # Name validation functions

    channel_name_regex = re.compile(r"^[a-zA-Z\d\-_.]+(\![\d\w\-_.]*)?$")
    group_name_regex = re.compile(r"^[a-zA-Z\d\-_.]+$")
    invalid_name_error = (
        "{} name must be a valid unicode string containing only ASCII "
        + "alphanumerics, hyphens, underscores, or periods."
    )

    def valid_channel_name(self, name, receive=False):
        """Tests whether a channel name is valid. A channel name can only contain ASCII
        alphanumeric, hyphen and periods.

        Args:
            name (str): Channel name to test
            receive (bool, optional): True if receive channel. Defaults to False.

        Raises:
            TypeError: If receiving channel is local it must end at the `!` character.
            TypeError: Channel name contains invalid characters.

        Returns:
            _type_: _True if channel name is valid.
        """
        if self.match_type_and_length(name):
            if bool(self.channel_name_regex.match(name)):
                # Check cases for special channels
                if "!" in name and not name.endswith("!") and receive:
                    raise TypeError(
                        "Specific channel names in receive() must end at the !"
                    )
                return True
        raise TypeError(
            "Channel name must be a valid unicode string containing only ASCII "
            + "alphanumerics, hyphens, or periods, not '{}'.".format(name)
        )

    def valid_group_name(self, name):
        """Tests whether a group name is valid. A group name can only contain ASCII
        alphanumeric, hyphen and periods.

        Args:
            name (str): group name to test.

        Raises:
            TypeError: Group name contains invalid characters.

        Returns:
            _type_: True if group name is valid.
        """
        if self.match_type_and_length(name):
            if bool(self.group_name_regex.match(name)):
                return True
        raise TypeError(
            "Group name must be a valid unicode string containing only ASCII "
            + "alphanumerics, hyphens, or periods."
        )

    def valid_channel_names(self, names, receive=False):
        """Tests whether a list of channel names is valid.

        Args:
            names List[str]: List of channel names to check
            receive (bool, optional): Channel names are receive channels. Defaults to False.

        Returns:
            bool : True if all valid.
        """
        _non_empty_list = True if names else False
        _names_type = isinstance(names, list)
        assert _non_empty_list and _names_type, "names must be a non-empty list"

        assert all(
            self.valid_channel_name(channel, receive=receive) for channel in names
        )
        return True

    def non_local_name(self, name):
        """
        Given a channel name, returns the "non-local" part. If the channel name
        is a process-specific channel (contains !) this means the part up to
        and including the !; if it is anything else, this means the full name.
        """
        if "!" in name:
            return name[: name.find("!") + 1]
        else:
            return name
