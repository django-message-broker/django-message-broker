import pytest

from django_message_broker import ChannelsServerLayer


@pytest.fixture()
@pytest.mark.asyncio
async def channel_layer():
    """
    Channel layer fixture that flushes automatically.
    """
    channel_layer = ChannelsServerLayer(capacity=3)
    yield channel_layer
    await channel_layer.flush()
    await channel_layer.close()


def test_get_routing_id(channel_layer):
    """
    Test that we can get a valid routing id.
    """

    routing_id = channel_layer.get_routing_id()
    assert isinstance(routing_id, str)
    assert len(routing_id) > 7
    assert routing_id[0:7] == "zmq_id_"
    routing_id_next = channel_layer.get_routing_id()
    assert routing_id == routing_id_next


def test_get_subscriber_id(channel_layer):
    """
    Test that we can get a valid subscriber id
    """
    subscriber_id = channel_layer.get_subscriber_id()
    assert isinstance(subscriber_id, bytes)
    assert len(subscriber_id) > 7
    assert subscriber_id.decode('utf8')[0:7] == "sub_id_"
    subscriber_id_next = channel_layer.get_subscriber_id()
    assert subscriber_id != subscriber_id_next
