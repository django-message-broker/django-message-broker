import unittest

import pytest
from django.test import override_settings

from channels import DEFAULT_CHANNEL_LAYER
from channels.exceptions import InvalidChannelLayerError
from channels.layers import channel_layers, get_channel_layer
from django_message_broker import ChannelsServerLayer


class TestChannelLayerManager(unittest.TestCase):
    @override_settings(
        CHANNEL_LAYERS={"default": {"BACKEND": "django_message_broker.ChannelsServerLayer"}}
    )
    def test_config_error(self):
        """
        If channel layer doesn't specify TEST_CONFIG, `make_test_backend`
        should result into error.
        """

        with self.assertRaises(InvalidChannelLayerError):
            channel_layers.make_test_backend(DEFAULT_CHANNEL_LAYER)

    @override_settings(
        CHANNEL_LAYERS={
            "default": {
                "BACKEND": "django_message_broker.ChannelsServerLayer",
                "TEST_CONFIG": {"expiry": 100500},
            }
        }
    )
    def test_config_instance(self):
        """
        If channel layer provides TEST_CONFIG, `make_test_backend` should
        return channel layer instance appropriate for testing.
        """

        layer = channel_layers.make_test_backend(DEFAULT_CHANNEL_LAYER)
        self.assertEqual(layer.expiry, 100500)

    def test_override_settings(self):
        """
        The channel layers cache is reset when the CHANNEL_LAYERS setting
        changes.
        """
        with override_settings(
            CHANNEL_LAYERS={
                "default": {"BACKEND": "django_message_broker.ChannelsServerLayer"}
            }
        ):
            self.assertEqual(channel_layers.backends, {})
            get_channel_layer()
            self.assertNotEqual(channel_layers.backends, {})
        self.assertEqual(channel_layers.backends, {})


# ChannelsServer layer tests

@pytest.mark.asyncio
async def test_send_receive():
    layer = ChannelsServerLayer()
    message = {"type": "test.message"}
    await layer.send("test.channel", message)
    assert message == await layer.receive("test.channel")
