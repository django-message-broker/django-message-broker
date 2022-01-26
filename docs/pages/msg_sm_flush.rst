=========================
Signalling message: Flush
=========================

Flushes all data from the client. Sends a message to all recently connected clients
to flush channels and messages from their stores.

This message blocks the client thread until a response is received from the server.

+---------------------+----------------------+-----------------------------+
| **Action**          | **Client -> Server** | **Server -> Client**        |
+=====================+======================+=============================+
|| **Initial action** || **Message**:        || Remove channel from group. |
||                    || ``b"FLUSHXXX"``     || Respond:                   |
||                    ||                     || -> Flush client            |
+---------------------+----------------------+-----------------------------+


The following message is sent from the server to all connected clients once the server
message store has been flushed. The clients must reset their message store to the 
initial state.

+-------------------+----------------------+-----------------------+
| **Action**        | **Server -> Client** | **Client -> Server**  |
+===================+======================+=======================+
|| **Flush client** || **Message**:        || No further response. |
||                  || ``b"FLUSHCXX"``     ||                      |
+-------------------+----------------------+-----------------------+
