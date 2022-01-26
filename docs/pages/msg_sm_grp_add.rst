================================
Signalling message: Add to group
================================

Adds a channel to a group. The channel name is the server channel name. The group may be set
to expire after a certain amount of time (``ttl``) in seconds. The expiry time is reset each
time a channel is added to the group. If channel is already part of the group then adding it
again will not add the channel a second time, but will reset the expiry time.

This message blocks the client thread until a response is received from the server.

+---------------------+----------------------------------------------+------------------------+
| **Action**          | **Client -> Server**                         | **Server -> Client**   |
+=====================+==============================================+========================+
|| **Initial action** || **Message**:                                || Add channel to group. |
||                    || ``b"GROUPADD"``                             || Respond:              |
||                    || **Properties**:                             || -> Complete           |
||                    || ``group_name (bytes)``: Name of group.      || -> Exception          |
||                    || ``channel_name (bytes)``: Name of channel.  ||                       |
||                    || ``ttl (float)``: Time until group expires.  ||                       |
+---------------------+----------------------------------------------+------------------------+
|| **Complete**       || **Message**:                                || No further action.    |
||                    || ``b"COMPLETE"``                             ||                       |
+---------------------+----------------------------------------------+------------------------+
|| **Exception**      || **Message**:                                || No further action.    |
||                    || ``b"EXCEPTON"``                             ||                       |
||                    || **Properties**:                             ||                       |
||                    || ``exception (str)``: Exception description. ||                       |
+---------------------+----------------------------------------------+------------------------+



