=============================
Data message: Send to channel
=============================

Messages sent from the client to a channel on the server. If the channel doesn't 
exist on the server then a channel will be created.

If the channel is full and ``ack`` is ``True`` then the server will send an exception back to the
client. If ``ack`` is ``False`` then the message will be dropped silently.

The client can specify two properties:

* **ttl (float)**: Time in seconds after the server receives the message that it will be deleted. If
  the message is forwarded to a client from the server then the time that the message is due to
  expire it must be passed to the client as a property (``expiry``) with the message.
* **ack (bool)**: ``True`` if the server should acknowledge the message. The client must wait until the
  server has acknowledged the message. If ack is ``False`` then the server must process the message
  silently without reporting any exceptions to the client.

If ``ack`` is ``true`` then the send function will block the thread until a response is received from
the server. If ``ack`` is ``false`` then execution will continue without waiting for a response.

+------------------------+---------------------------------------------+-------------------------------------+
| **Action**             | **Client -> Server**                        | **Server -> Client**                |
+========================+=============================================+=====================================+
|| **Initial action**    || **Message**:                               || Add message to queue.              |
||                       || ``b"SENDCHAN"``                            || If no queue, create queue.         |
||                       || **Properties**:                            || If ``ack`` = ``False``:            |
||                       || ``ttl (float)``: Time to live in seconds.  || -> No response.                    |
||                       || ``ack (bool)``: Acknowledge task complete. || If ``ack`` = ``True``:             |
||                       ||                                            || -> Respond complete.               |
||                       ||                                            || -> Respond exception.              |
+------------------------+---------------------------------------------+-------------------------------------+
|| **Respond complete**  ||                                            || **Message**:                       |
||                       ||                                            || ``b"COMPLETE"``                    |
+------------------------+---------------------------------------------+-------------------------------------+
|| **Respond exception** ||                                            || **Message**:                       |
||                       ||                                            || ``b"EXCEPTON"``                    |
||                       ||                                            || **Properties**:                    |
||                       ||                                            || ``exception (str)``: Error message |
+------------------------+---------------------------------------------+-------------------------------------+
