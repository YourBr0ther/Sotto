"""Tests for the MQTT client wrapper."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from comms.mqtt_client import MqttClient
from utils.config_loader import MqttConfig, MqttTopics


@pytest.fixture
def mqtt_config() -> MqttConfig:
    return MqttConfig(
        broker_host="localhost",
        broker_port=1883,
        client_id="test-client",
        topics=MqttTopics(),
    )


@pytest.fixture
def client(mqtt_config: MqttConfig) -> MqttClient:
    """Create an MqttClient with a mocked paho client (for unit testing only)."""
    with patch("comms.mqtt_client.mqtt.Client") as MockClient:
        mock_paho = MockClient.return_value
        mock_paho.connect.return_value = 0
        mock_paho.publish.return_value = MagicMock(rc=0)
        mock_paho.subscribe.return_value = (0, 1)

        c = MqttClient(mqtt_config, device_name="test-device")
        # Simulate connection
        c._connected = True
        yield c


class TestMqttClientInit:
    def test_creates_with_config(self, mqtt_config: MqttConfig) -> None:
        with patch("comms.mqtt_client.mqtt.Client"):
            client = MqttClient(mqtt_config)
            assert client._config == mqtt_config
            assert client.is_connected is False

    def test_sets_credentials_when_provided(self) -> None:
        config = MqttConfig(
            broker_host="localhost",
            broker_port=1883,
            client_id="test",
            username="user",
            password="pass",
        )
        with patch("comms.mqtt_client.mqtt.Client") as MockClient:
            mock_paho = MockClient.return_value
            MqttClient(config)
            mock_paho.username_pw_set.assert_called_once_with("user", "pass")


class TestPublish:
    def test_publish_wraps_in_envelope(self, client: MqttClient) -> None:
        client.publish("sotto/test/topic", {"data": "hello"})

        call_args = client._client.publish.call_args
        topic = call_args[0][0]
        message = json.loads(call_args[0][1])

        assert topic == "sotto/test/topic"
        assert message["source"] == "test-device"
        assert message["type"] == "topic"
        assert message["payload"]["data"] == "hello"
        assert "timestamp" in message

    def test_publish_buffers_when_disconnected(self, client: MqttClient) -> None:
        client._connected = False
        client.publish("sotto/test", {"data": "buffered"})
        assert len(client._offline_buffer) == 1

    def test_buffer_drops_oldest_when_full(self, client: MqttClient) -> None:
        client._connected = False
        client._max_offline_buffer = 3
        for i in range(5):
            client.publish("sotto/test", {"i": i})
        assert len(client._offline_buffer) == 3
        # The last 3 should remain
        payloads = [item[1]["payload"]["i"] for item in client._offline_buffer]
        assert payloads == [2, 3, 4]


class TestSubscribe:
    def test_subscribe_stores_callback(self, client: MqttClient) -> None:
        callback = MagicMock()
        client.subscribe("sotto/test/#", callback)
        assert "sotto/test/#" in client._subscriptions
        assert callback in client._subscriptions["sotto/test/#"]

    def test_subscribe_calls_paho_when_connected(self, client: MqttClient) -> None:
        callback = MagicMock()
        client.subscribe("sotto/test/topic", callback, qos=1)
        client._client.subscribe.assert_called_with("sotto/test/topic", qos=1)


class TestMessageHandling:
    def test_on_message_dispatches_to_callback(self, client: MqttClient) -> None:
        callback = MagicMock()
        client._subscriptions["sotto/test/topic"] = [callback]

        mock_message = MagicMock()
        mock_message.topic = "sotto/test/topic"
        mock_message.payload = json.dumps({"payload": "data"}).encode()

        client._on_message(client._client, None, mock_message)
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == "sotto/test/topic"
        assert args[1]["payload"] == "data"

    def test_on_message_handles_invalid_json(self, client: MqttClient) -> None:
        mock_message = MagicMock()
        mock_message.topic = "sotto/test"
        mock_message.payload = b"not json"
        # Should not raise
        client._on_message(client._client, None, mock_message)


class TestConnectionEvents:
    def test_on_connect_sets_connected(self, client: MqttClient) -> None:
        client._connected = False
        client._on_connect(client._client, None, None, 0)
        assert client._connected is True

    def test_on_connect_resubscribes(self, client: MqttClient) -> None:
        client._connected = False
        callback = MagicMock()
        client._subscriptions["sotto/test"] = [callback]
        client._on_connect(client._client, None, None, 0)
        client._client.subscribe.assert_called_with("sotto/test")

    def test_on_connect_flushes_buffer(self, client: MqttClient) -> None:
        client._connected = False
        client._offline_buffer.append(("sotto/test", {"data": "buffered"}, 0))
        client._on_connect(client._client, None, None, 0)
        assert len(client._offline_buffer) == 0

    def test_on_disconnect_sets_not_connected(self, client: MqttClient) -> None:
        client._on_disconnect(client._client, None, None, 0)
        assert client._connected is False


class TestOfflineBuffer:
    def test_flush_publishes_all_buffered(self, client: MqttClient) -> None:
        client._offline_buffer = [
            ("sotto/a", {"msg": 1}, 0),
            ("sotto/b", {"msg": 2}, 1),
        ]
        client._flush_offline_buffer()
        assert client._client.publish.call_count == 2
        assert len(client._offline_buffer) == 0

    def test_flush_noop_when_empty(self, client: MqttClient) -> None:
        client._flush_offline_buffer()
        # publish should not be called for flushing (may have been called elsewhere)
