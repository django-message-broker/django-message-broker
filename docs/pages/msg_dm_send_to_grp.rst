===========================
Data message: Send to group
===========================

Messages sent from the client to a group of channels on the server. If the group doesn't 
exist on the server or no channels have been added to the group then the message must be
silently dropped.

The client can specify one property:

* ``ttl (float)`` : Time in seconds after the server receives the message that it will be deleted. If
  the message is forwarded to a client from the server then the time that the message is due to
  expire is must be passed to the client as a property (``expiry``) with the message.

+---------------------+--------------------------------------------+------------------------------+
| **Action**          | **Client -> Server**                       | **Server -> Client**         |
+=====================+============================================+==============================+
|| **Initial action** || **Message**:                              || Send message to channels in |
||                    || ``b"SENDCHAN"``                           || group.                      |
||                    || **Properties**:                           ||                             |
||                    || ``ttl (float)``: Time to live in seconds. ||                             |
+---------------------+--------------------------------------------+------------------------------+
