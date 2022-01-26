=========
Messaging
=========

Messaging between the client and server uses Zero Message Queue (ZMQ) as the
transport protocol. Two communication channels are established, one to 
communicate signalling information and the other for data. Signalling is carried
over a separate channel to minimise the chance that data messages block communication
between the client and server. The data channel defaults to port 5556 and signalling
to port 5557.

Note: The client-server communication is implemented using a ZMQ Dealer at the client
and a ZMQ Router at the server. This allows multiple clients to connect to the server.
Each message from the client has a routing ID prepended by the ZMQ Dealer which needs
to be removed at the server prior to processing the message. If there are additional
routing nodes between the client and the server then ZMQ may add multiple routing IDs to
the message.  All routing IDs are removed and recorded at the server so that messages
can be routed back to the originating client, even where multi-hop ZMQ networks are used.
Whilst this doesn't apply over localhost networks for which the message broker is designed,
there may be future developments which allow the message broker to be deployed on a 
different server from the client and with additional routing nodes to support multi-server
deployments.

The following signalling sequences are supported: 

.. toctree::
    :maxdepth: 2
    :glob:

    msg_*
