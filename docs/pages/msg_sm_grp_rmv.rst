=====================================
Signalling message: Remove from group
=====================================

Removes a channel from a group. The channel name is the server channel name.

This message blocks the client thread until a response is received from the server.

+---------------------+----------------------------------------------+-----------------------------+
| **Action**          | **Client -> Server**                         | **Server -> Client**        |
+=====================+==============================================+=============================+
|| **Initial action** || **Message**:                                || Remove channel from group. |
||                    || ``b"GROUPDIS"``                             || Respond:                   |
||                    || **Properties**:                             || -> Complete                |
||                    || ``group_name (bytes)``: Name of group.      || -> Exception               |
||                    || ``channel_name (bytes)``: Name of channel.  ||                            |
+---------------------+----------------------------------------------+-----------------------------+
|| **Complete**       || **Message**:                                || No further action.         |
||                    || ``b"COMPLETE"``                             ||                            |
+---------------------+----------------------------------------------+-----------------------------+
|| **Exception**      || **Message**:                                || No further action.         |
||                    || ``b"EXCEPTON"``                             ||                            |
||                    || **Properties**:                             ||                            |
||                    || ``exception (str)``: Exception description. ||                            |
+---------------------+----------------------------------------------+-----------------------------+
