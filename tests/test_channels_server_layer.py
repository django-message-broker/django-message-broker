import asyncio

import async_timeout
import pytest

from channels.exceptions import ChannelFull
from django_message_broker import ChannelsServerLayer


@pytest.fixture()
async def channel_layer():
    """
    Channel layer fixture that flushes automatically.
    """
    channel_layer = ChannelsServerLayer(capacity=3)
    yield channel_layer
    await channel_layer.flush()
    await channel_layer.close()


@pytest.mark.asyncio
async def test_send_receive(channel_layer):
    """
    Makes sure we can send a message to a normal channel then receive it.
    """
    await channel_layer.send(
        "test-channel-1", {"type": "test.message", "text": "Ahoy-hoy!"}
    )
    message = await channel_layer.receive("test-channel-1")
    assert message["type"] == "test.message"
    assert message["text"] == "Ahoy-hoy!"


@pytest.mark.asyncio
async def test_send_capacity(channel_layer):
    """
    Makes sure we get ChannelFull when we hit the send capacity.

    This test doesn't make sense when the capacity constraints are in the server and
    on the processing of the receive queue. Consider alternative tests for capacity.
    """
    pass
    # await channel_layer.send("test-channel-1", {"type": "test.message"})
    # await channel_layer.send("test-channel-1", {"type": "test.message"})
    # await channel_layer.send("test-channel-1", {"type": "test.message"})
    # with pytest.raises(ChannelFull):
    #     await channel_layer.send("test-channel-1", {"type": "test.message"})


@pytest.mark.asyncio
async def test_process_local_send_receive(channel_layer):
    """
    Makes sure we can send a message to a process-local channel then receive it.
    """
    channel_name = await channel_layer.new_channel()
    await channel_layer.send(
        channel_name, {"type": "test.message", "text": "Local only please"}
    )
    message = await channel_layer.receive(channel_name)
    assert message["type"] == "test.message"
    assert message["text"] == "Local only please"


@pytest.mark.asyncio
async def test_multi_send_receive(channel_layer):
    """
    Tests overlapping sends and receives, and ordering.
    """
    channel_layer = ChannelsServerLayer()
    await channel_layer.send("test-channel-3", {"type": "message.1"})
    await channel_layer.send("test-channel-3", {"type": "message.2"})
    await channel_layer.send("test-channel-3", {"type": "message.3"})
    assert (await channel_layer.receive("test-channel-3"))["type"] == "message.1"
    assert (await channel_layer.receive("test-channel-3"))["type"] == "message.2"
    assert (await channel_layer.receive("test-channel-3"))["type"] == "message.3"


@pytest.mark.asyncio
async def test_groups_basic(channel_layer):
    """
    Tests basic group operation.

    ISSUE: Message is sent before group operations are completed on the server.
    Therefore, message is sent to group before channels two and three are added.
    Temp solution is to wait for operations to complete.
    Full solution is to block execution until confirmation that signalling message complete.
    """
    channel_layer = ChannelsServerLayer()
    await channel_layer.group_add("test-group", "test-gr-chan-1")
    await channel_layer.group_add("test-group", "test-gr-chan-2")
    await channel_layer.group_add("test-group", "test-gr-chan-3")
    await channel_layer.group_discard("test-group", "test-gr-chan-2")
    await asyncio.sleep(1.0)
    await channel_layer.group_send("test-group", {"type": "message.1"})
    # Make sure we get the message on the two channels that were in
    async with async_timeout.timeout(1):
        assert (await channel_layer.receive("test-gr-chan-1"))["type"] == "message.1"
        assert (await channel_layer.receive("test-gr-chan-3"))["type"] == "message.1"
    # Make sure the removed channel did not get the message
    with pytest.raises(asyncio.TimeoutError):
        async with async_timeout.timeout(1):
            await channel_layer.receive("test-gr-chan-2")


@pytest.mark.asyncio
async def test_groups_channel_full(channel_layer):
    """
    Tests that group_send ignores ChannelFull
    """
    channel_layer = ChannelsServerLayer()
    await channel_layer.group_add("test-group", "test-gr-chan-1")
    await channel_layer.group_send("test-group", {"type": "message.1"})
    await channel_layer.group_send("test-group", {"type": "message.1"})
    await channel_layer.group_send("test-group", {"type": "message.1"})
    await channel_layer.group_send("test-group", {"type": "message.1"})
    await channel_layer.group_send("test-group", {"type": "message.1"})


@pytest.mark.asyncio
async def test_expiry_single(channel_layer):
    """
    Tests that a message can expire.

    Changes in test compared with Django Channels:

    1. Use channel_layer setup
    2. Explicitly set properties: expiry=0.1, channel_time_to_live=0.1
    3. Send and receive an initial message to force creation of channel locally
    4. Insert one second wait before final test that the channel queue is removed
    """
    # Set message time to live for messages that are sent.
    channel_layer.expiry = 0.1
    # Set expiry time for channels.
    channel_layer.channel_time_to_live = 0.1

    await channel_layer.send("test-channel-1", {"type": "message.0"})
    await channel_layer.receive("test-channel-1")

    await channel_layer.send("test-channel-1", {"type": "message.1"})
    assert len(channel_layer.channels) == 1

    await asyncio.sleep(1.5)

    # Message should have expired and been dropped.
    with pytest.raises(asyncio.TimeoutError):
        async with async_timeout.timeout(1):
            await channel_layer.receive("test-channel-1")

    await asyncio.sleep(1.1)

    # Channel should be cleaned up.
    assert len(channel_layer.channels) == 0


@pytest.mark.asyncio
async def test_expiry_unread(channel_layer):
    """
    Tests that a message on a channel can expire and be cleaned up even if
    the channel is not read from again.

    Changes in test compared with Django Channels:

    1. Use channel_layer setup
    2. Explicitly set properties: expiry=0.1, channel_time_to_live=0.1
    3. Send and receive an initial message to force creation of channel locally
    4. Insert two second wait before final test that the channel queue is removed
    """
    # Set message time to live for messages that are sent.
    channel_layer.expiry = 0.1
    # Set expiry time for channels.
    channel_layer.channel_time_to_live = 0.1

    # Need to create pull channels from server.
    await channel_layer.send("test-channel-1", {"type": "message.0"})
    await channel_layer.receive("test-channel-1")
    await channel_layer.send("test-channel-2", {"type": "message.0"})
    await channel_layer.receive("test-channel-2")

    await channel_layer.send("test-channel-1", {"type": "message.1"})

    await asyncio.sleep(0.1)

    await channel_layer.send("test-channel-2", {"type": "message.2"})
    assert len(channel_layer.channels) == 2
    assert (await channel_layer.receive("test-channel-2"))["type"] == "message.2"
    # Both channels should be cleaned up.

    await asyncio.sleep(2.0)

    assert len(channel_layer.channels) == 0


@pytest.mark.asyncio
async def test_expiry_multi(channel_layer):
    """
    Tests that multiple messages can expire.

    Changes in test compared with Django Channels:

    1. Use channel_layer setup
    2. Explicitly set properties: expiry=0.1, channel_time_to_live=0.1
    3. Increased wait before sending message 4
    4. Increased wait before testing that all channels deleted.
    """
    # Set message time to live for messages that are sent.
    channel_layer.expiry = 0.1
    # Set expiry time for channels.
    channel_layer.channel_time_to_live = 0.1

    await channel_layer.send("test-channel-1", {"type": "message.1"})
    await channel_layer.send("test-channel-1", {"type": "message.2"})
    await channel_layer.send("test-channel-1", {"type": "message.3"})
    assert (await channel_layer.receive("test-channel-1"))["type"] == "message.1"

    await asyncio.sleep(1.1)
    await channel_layer.send("test-channel-1", {"type": "message.4"})
    assert (await channel_layer.receive("test-channel-1"))["type"] == "message.4"

    # The second and third message should have expired and been dropped.
    with pytest.raises(asyncio.TimeoutError):
        async with async_timeout.timeout(0.5):
            await channel_layer.receive("test-channel-1")

    # Channel should be cleaned up.
    await asyncio.sleep(1.0)

    assert len(channel_layer.channels) == 0
