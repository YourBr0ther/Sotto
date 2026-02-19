"""MQTT client wrapper for Sotto edge device communication."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

import paho.mqtt.client as mqtt

from utils.config_loader import MqttConfig

logger = logging.getLogger(__name__)

MessageCallback = Callable[[str, dict[str, Any]], None]


class MqttClient:
    """MQTT client for communication with the Sotto home server.

    Handles connection, reconnection, publishing, and subscribing
    with the standard Sotto message envelope format.
    """

    def __init__(self, config: MqttConfig, device_name: str = "sotto-phone") -> None:
        self._config = config
        self._device_name = device_name
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
        )
        self._connected = False
        self._subscriptions: dict[str, list[MessageCallback]] = {}
        self._offline_buffer: list[tuple[str, dict[str, Any], int]] = []
        self._max_offline_buffer = 1000

        # Set up callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        # Set credentials if provided
        if config.username and config.password:
            self._client.username_pw_set(config.username, config.password)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Connect to the MQTT broker.

        Raises:
            ConnectionError: If the broker is unreachable.
        """
        try:
            self._client.connect(
                self._config.broker_host,
                self._config.broker_port,
            )
            self._client.loop_start()
            logger.info(
                "Connecting to MQTT broker at %s:%d",
                self._config.broker_host,
                self._config.broker_port,
            )
        except Exception as e:
            logger.error("Failed to connect to MQTT broker: %s", e)
            raise ConnectionError(f"MQTT connection failed: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        self._client.loop_stop()
        self._client.disconnect()
        self._connected = False
        logger.info("Disconnected from MQTT broker")

    def publish(self, topic: str, payload: dict[str, Any], qos: int = 0) -> None:
        """Publish a message with the standard Sotto envelope.

        Args:
            topic: MQTT topic to publish to.
            payload: Message payload (will be wrapped in envelope).
            qos: MQTT QoS level (0, 1, or 2).
        """
        envelope = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self._device_name,
            "type": topic.split("/")[-1],
            "payload": payload,
        }
        message = json.dumps(envelope)

        if self._connected:
            result = self._client.publish(topic, message, qos=qos)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning("Publish to %s failed (rc=%d), buffering", topic, result.rc)
                self._buffer_message(topic, envelope, qos)
            else:
                logger.debug("Published to %s", topic)
        else:
            self._buffer_message(topic, envelope, qos)

    def subscribe(self, topic: str, callback: MessageCallback, qos: int = 0) -> None:
        """Subscribe to an MQTT topic with a callback.

        Args:
            topic: MQTT topic pattern to subscribe to.
            callback: Function called with (topic, payload_dict) on message receipt.
            qos: MQTT QoS level for the subscription.
        """
        if topic not in self._subscriptions:
            self._subscriptions[topic] = []
        self._subscriptions[topic].append(callback)

        if self._connected:
            self._client.subscribe(topic, qos=qos)
            logger.info("Subscribed to %s", topic)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: Any,
        properties: Any = None,
    ) -> None:
        """Handle successful connection."""
        self._connected = True
        logger.info("Connected to MQTT broker (rc=%s)", rc)

        # Resubscribe to all topics
        for topic in self._subscriptions:
            self._client.subscribe(topic)
            logger.debug("Resubscribed to %s", topic)

        # Flush offline buffer
        self._flush_offline_buffer()

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any = None,
        rc: Any = None,
        properties: Any = None,
    ) -> None:
        """Handle disconnection."""
        self._connected = False
        if rc != 0:
            logger.warning("Unexpected MQTT disconnection (rc=%s)", rc)
        else:
            logger.info("MQTT disconnected cleanly")

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        """Handle incoming message."""
        topic = message.topic
        try:
            data = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Failed to decode message on %s: %s", topic, e)
            return

        # Find matching subscriptions (exact match or wildcard)
        for sub_topic, callbacks in self._subscriptions.items():
            if mqtt.topic_matches_sub(sub_topic, topic):
                for callback in callbacks:
                    try:
                        callback(topic, data)
                    except Exception as e:
                        logger.error("Callback error on %s: %s", topic, e)

    def _buffer_message(self, topic: str, envelope: dict[str, Any], qos: int) -> None:
        """Buffer a message for later delivery."""
        if len(self._offline_buffer) >= self._max_offline_buffer:
            self._offline_buffer.pop(0)  # Drop oldest
            logger.warning("Offline buffer full, dropping oldest message")
        self._offline_buffer.append((topic, envelope, qos))
        logger.debug("Buffered message for %s (buffer_size=%d)", topic, len(self._offline_buffer))

    def _flush_offline_buffer(self) -> None:
        """Publish all buffered messages."""
        if not self._offline_buffer:
            return
        count = len(self._offline_buffer)
        buffer = self._offline_buffer.copy()
        self._offline_buffer.clear()
        for topic, envelope, qos in buffer:
            message = json.dumps(envelope)
            self._client.publish(topic, message, qos=qos)
        logger.info("Flushed %d buffered messages", count)
