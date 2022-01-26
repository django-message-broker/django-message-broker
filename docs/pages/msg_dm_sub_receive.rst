===================================
Data message: Subscribe and receive
===================================

This messaging flow allows the client to subscribe to a channel and then automatically
receive messages in a local subscriber queue. The application can then pull messages from
this queue as required. This approach removes messages from the server and stores them
locally to reduce load on the server and reduce latency when pulling messages.

The messaging flow comprises two sub-flows:

 * Messaging flow for the client to subscribe to the channel
 * Messaging flow for the server to forward messages to local client storage

Subscribe to channel
^^^^^^^^^^^^^^^^^^^^
Send a message to the server requesting subscription to a channel. The client provides the name
of the local queue set up to store and forward messages to the local subscriber.

If the ``expiry`` property is set within a received message then the message must be removed from
the local queue once the expiry time is reached.

To support Django Channels, if the channel name includes an ``!`` then the channel is classed
as local and can only have one subscriber.

+---------------------+-----------------------------------------------------+----------------------+
| **Action**          | **Client -> Server**                                | **Server -> Client** |
+=====================+=====================================================+======================+
|| **Initial action** || **Message**:                                       || No further action.  |
||                    || ``b"SUBCHANX"``                                    ||                     |
||                    || **Channel name**:                                  ||                     |
||                    || Channel name on the server                         ||                     |
||                    || **Properties**:                                    ||                     |
||                    || ``subscriber_name (str)`` = Local subscriber name. ||                     |
+---------------------+-----------------------------------------------------+----------------------+


Forward message to client
^^^^^^^^^^^^^^^^^^^^^^^^^
Forward a message from a channel queue on the server to a local queue at the client. A message is
sent from the server when there is at least one message in the queue and at least one client
subscribed to the queue. If the channel is a local channel (name contains ``!``) then only one
subscriber is permitted to the channel queue at the server. If there is more than one subscriber
to the queue then messages are delivered to each queue in turn using the *round robin* pattern.

+-----------------------+---------------------------------------------------+----------------------+
| **Action**            | **Server -> Client**                              | **Client -> Server** |
+=======================+===================================================+======================+
|| **Triggered action** || **Message**:                                     || No further action.  |
||                      || ``b"DELIVERY"``                                  ||                     |
||                      || **Channel name**:                                ||                     |
||                      || Local subscriber name                            ||                     |
||                      || **Properties**:                                  ||                     |
||                      || ``expiry (DateTime)``: Time the message expires. ||                     |
+-----------------------+---------------------------------------------------+----------------------+

