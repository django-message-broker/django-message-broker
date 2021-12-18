import asyncio
from typing import List
from multiprocessing import Process

from zmq.eventloop.zmqstream import ZMQStream
from server.signalling_message import SignallingMessage, SignallingMessageCommands
from server.data_message import DataMessage, DataMessageCommands
from server.channels_server import ChannelsServer
from tornado.ioloop import IOLoop

import time
import zmq


class ChannelServerTest:
    def __init__(self):

        # Create a background process for the server and start the server within it.
        self.background_process = Process(
            name="background", target=self.channels_background_server
        )
        self.background_process.daemon = True
        self.background_process.start()

        # Create event loop
        self.ioloop = IOLoop.current()

        # TEST: Create client
        print("CLIENT: Initialising client")
        port = 5556
        ctx = zmq.Context()

        # Create socket for data
        self.data_socket = ctx.socket(zmq.DEALER)
        self.data_socket.connect(f"tcp://127.0.0.1:{port}")
        self.data_stream = ZMQStream(self.data_socket, self.ioloop)
        self.data_stream.on_recv(self.receive_data)

        # Create socket for signalling
        self.signalling_socket = ctx.socket(zmq.DEALER)
        self.signalling_socket.connect(f"tcp://127.0.0.1:{port+1}")
        self.signalling_lock = asyncio.Event()
        self.signalling_stream = ZMQStream(self.signalling_socket, self.ioloop)
        self.signalling_stream.on_recv(self.receive_signalling)

    def run(self):
        self.ioloop.run_sync(self.tests)

    async def tests(self):
        print("TEST: Start tests.")

        await self.test_data_message()
        await self.test_group_add()
        await self.test_group_send()
        await self.test_flush()
        await self.test_data_message()
        await self.test_group_add()
        await self.test_group_send()
        await self.test_local_channel_change()

        print_message_store = SignallingMessage(
            command=b"PRINTXXX",
        )
        await self.send_receive_signalling(print_message_store)
        print("TEST: End tests.")
        await asyncio.sleep(5)
        print("TEST: End sleep.")

    def channels_background_server(self):
        self.background_worker = ChannelsServer()
        self.background_worker.start()

    def receive_data(self, multipart_message: List):
        try:
            message = DataMessage.from_msg(multipart_message)
            if message.command == DataMessageCommands.DELIVERY:
                print(
                    f"CLIENT: RM : {message.command} {message.channel_name} {message.body}"
                )
            elif message.command == DataMessageCommands.SUBSCRIPTION_ERROR:
                print(
                    f"CLIENT: REC ERROR : {message.command} {message.channel_name} {message.properties}"
                )
        except Exception as e:
            print("Error")
            raise ImportError(e)

    def receive_signalling(self, multipart_message: List):
        try:
            message = SignallingMessage.from_msg(multipart_message)
            self.signalling_lock.set()
            print(f"CLIENT: RS: {message.command} {message.properties}")
        except Exception as e:
            print("Error")
            raise ImportError(e)

    async def send_receive_signalling(self, send_message: SignallingMessage):
        print(f"CLIENT: SS : {send_message.command} {send_message.properties}")
        self.signalling_lock.clear()
        await send_message.send(self.signalling_socket)
        await self.signalling_lock.wait()

    async def send_data_message(self, message: DataMessage):
        print(f"CLIENT: SM: {message.command} {message.body}")
        await message.send(self.data_socket)

    async def send_signalling_message(self, message: SignallingMessage):
        await message.send(self.signalling_socket)

    async def test_data_message(self):

        # TEST Subscribe to channel
        test_data_message = DataMessage(
            channel_name=b"sourcepress",
            command=DataMessageCommands.SUBSCRIBE,
            sequence=0,
            properties={"ttl": 5, "local_id": "01234"},
        )
        print("CLIENT: Subscribe to channel")
        await self.send_data_message(test_data_message)

        # TEST Send data messages
        print("CLIENT: Send message")
        test_data_message.command = DataMessageCommands.SEND_TO_CHANNEL
        test_data_message.body = {"Message": "First"}
        await self.send_data_message(test_data_message)
        await asyncio.sleep(1)
        test_data_message.body = {"Message": "Second"}
        await self.send_data_message(test_data_message)
        await asyncio.sleep(1)
        test_data_message.body = {"Message": "Third"}
        await self.send_data_message(test_data_message)
        test_data_message.body = {"Message": "Fourth"}
        await self.send_data_message(test_data_message)

    async def test_group_add(self):
        test_signalling_message = SignallingMessage(
            command=SignallingMessageCommands.GROUP_ADD,
            properties={
                "group_name": "GroupA",
                "channel_name": "ChannelA",
                "ttl": 86400,
            },
        )
        await self.send_receive_signalling(test_signalling_message)

    async def test_flush(self):
        print("CLIENT: Flushing message store.")
        flush_message = SignallingMessage(
            command=SignallingMessageCommands.FLUSH,
        )
        await self.send_receive_signalling(flush_message)
        print_message_store = SignallingMessage(
            command=b"PRINTXXX",
        )
        await self.send_receive_signalling(print_message_store)

    async def test_group_send(self):
        print("CLIENT: Subscribe to channel.")
        subscribe_message = DataMessage(
            channel_name=b"sourcepress",
            command=DataMessageCommands.SUBSCRIBE,
        )
        print("CLIENT: Add to group.")
        await subscribe_message.send(self.data_socket)

        add_group_message = SignallingMessage(
            command=SignallingMessageCommands.GROUP_ADD,
            properties={"group_name": "my-group", "channel_name": "sourcepress"},
        )
        print("CLIENT: Send to group.")
        await self.send_receive_signalling(add_group_message)
        group_message = DataMessage(
            command=DataMessageCommands.SEND_TO_GROUP,
            channel_name=b"my-group",
            body={"message": "This is a group message."},
        )
        await group_message.send(self.data_socket)
        print("CLIENT: Message sent to server")
        await asyncio.sleep(1)

    async def test_local_channel_change(self):
        print("Subscribe to process channel")
        process_channel_subscribe = DataMessage(
            channel_name=b"channel_A",
            command=DataMessageCommands.SUBSCRIBE,
            sequence=0,
            properties={"TTL": 60, "local_id": "01234"},
        )
        await process_channel_subscribe.send(self.data_socket)

        print("Subscribe to channel without process_local")
        subscribe_without_local = DataMessage(
            channel_name=b"channel_A",
            command=DataMessageCommands.SUBSCRIBE,
            sequence=0,
            properties={"TTL": 60},
        )
        await subscribe_without_local.send(self.data_socket)


cst = ChannelServerTest()
cst.run()


time.sleep(5)
