"""Sotto Edge Device - Main entry point.

Runs the ambient AI assistant edge device on Android (Termux) or Raspberry Pi 5.
Handles audio capture, wake word detection, state management, and MQTT communication.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from audio.input import PhoneMicInput
from audio.noise_filter import NoiseFilter
from audio.output import HeadphoneMonitor, SpeakerOutput
from audio.wake_word import WakeWordDetector
from comms.audio_streamer import AudioStreamer
from comms.mqtt_client import MqttClient
from state.device_state import AgentMode, DeviceState, QueuedMessage
from utils.config_loader import SottoConfig, load_config
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


class SottoEdgeDevice:
    """Main application class for the Sotto edge device."""

    def __init__(self, config: SottoConfig) -> None:
        self._config = config
        self._running = False

        # Core components
        self._state = DeviceState()
        self._mqtt = MqttClient(config.mqtt, device_name=config.device.name)
        self._noise_filter = NoiseFilter(
            sample_rate=config.audio.sample_rate,
        )
        self._audio_input = PhoneMicInput(
            device_index=config.audio.input_device,
            sample_rate=config.audio.sample_rate,
        )
        self._audio_output = SpeakerOutput(device_index=config.audio.output_device)
        self._audio_streamer = AudioStreamer(
            mqtt_client=self._mqtt,
            noise_filter=self._noise_filter,
            topic=config.mqtt.topics.audio_stream,
            sample_rate=config.audio.sample_rate,
        )
        self._headphone_monitor = HeadphoneMonitor(
            platform=config.device.type if config.device.type in ("android", "linux") else "android"
        )
        self._wake_word = WakeWordDetector(
            model_name=config.wake_word.model,
            threshold=config.wake_word.threshold,
        )

        # State
        self._wake_word_active = False
        self._command_buffer: list[bytes] = []

    def start(self) -> None:
        """Start the edge device application."""
        logger.info("Starting Sotto edge device: %s (%s)", self._config.device.name, self._config.device.type)
        self._running = True

        # Connect MQTT
        try:
            self._mqtt.connect()
        except ConnectionError:
            logger.warning("MQTT connection failed, will retry in background")

        # Subscribe to incoming topics
        self._setup_subscriptions()

        # Initialize wake word (non-fatal if it fails)
        try:
            self._wake_word.initialize()
            self._wake_word.set_callback(self._on_wake_word_detected)
        except (ImportError, RuntimeError) as e:
            logger.warning("Wake word unavailable: %s. Continuing without it.", e)

        # Start audio capture
        try:
            self._audio_input.start_capture()
        except Exception as e:
            logger.error("Audio capture failed to start: %s", e)
            raise

        # Start headphone monitoring in background
        headphone_thread = threading.Thread(target=self._headphone_monitor_loop, daemon=True)
        headphone_thread.start()

        # Main audio processing loop
        logger.info("Sotto edge device running. Press Ctrl+C to stop.")
        self._main_loop()

    def stop(self) -> None:
        """Stop the edge device application."""
        logger.info("Stopping Sotto edge device")
        self._running = False

        # Publish offline state
        try:
            self._mqtt.publish(
                self._config.mqtt.topics.device_state,
                self._state.to_dict() | {"status": "offline"},
                qos=1,
            )
        except Exception:
            pass

        self._audio_input.stop_capture()
        self._mqtt.disconnect()
        logger.info("Sotto edge device stopped")

    def _main_loop(self) -> None:
        """Main audio processing loop."""
        chunk_ms = self._config.audio.chunk_duration_ms

        while self._running:
            try:
                if not self._state.should_process_audio():
                    time.sleep(0.5)
                    continue

                # Read audio chunk
                chunk = self._audio_input.read_chunk(duration_ms=chunk_ms)

                if not chunk:
                    continue

                # Check for wake word
                if self._wake_word.is_enabled:
                    self._wake_word.process_audio(chunk, self._config.audio.sample_rate)

                # Stream to server
                if self._state.should_process_audio():
                    self._audio_streamer.stream_chunk(chunk)

                # Periodic state update
                if self._audio_streamer.chunks_sent % 20 == 0:
                    self._publish_device_state()

            except Exception as e:
                logger.error("Error in main loop: %s", e)
                time.sleep(1)

    def _setup_subscriptions(self) -> None:
        """Set up MQTT topic subscriptions."""
        topics = self._config.mqtt.topics

        # TTS text from server (to be synthesized locally)
        self._mqtt.subscribe(topics.tts_text, self._on_tts_text, qos=1)

        # Heartbeat messages
        self._mqtt.subscribe(topics.heartbeat, self._on_heartbeat, qos=1)

        # Notifications
        self._mqtt.subscribe(topics.notifications, self._on_notification, qos=1)

        # Agent mode commands from server
        self._mqtt.subscribe(topics.agent_mode, self._on_mode_change, qos=1)

    def _on_wake_word_detected(self) -> None:
        """Handle wake word detection."""
        logger.info("Wake word detected!")
        self._wake_word_active = True

        # Publish wake word event to server
        self._mqtt.publish(
            self._config.mqtt.topics.commands,
            {"command": "wake_word_activated"},
            qos=1,
        )

    def _on_tts_text(self, topic: str, data: dict[str, Any]) -> None:
        """Handle TTS text from server - play through output."""
        payload = data.get("payload", data)
        text = payload.get("text", "")

        if self._state.should_play_output():
            logger.info("Received TTS text: %s", text[:50])
            # In Phase 1, TTS synthesis happens server-side and audio is sent
            # For now, log the text. Full TTS pipeline is in the server.
        else:
            self._state.queue_output(
                QueuedMessage(
                    content=text,
                    priority=payload.get("priority", 5),
                    content_type="tts",
                )
            )

    def _on_heartbeat(self, topic: str, data: dict[str, Any]) -> None:
        """Handle heartbeat notification from server."""
        payload = data.get("payload", data)
        if self._state.should_play_output():
            logger.info("Heartbeat received: %s", str(payload)[:100])
        else:
            self._state.queue_output(
                QueuedMessage(
                    content=json.dumps(payload),
                    priority=payload.get("priority", 3),
                    content_type="heartbeat",
                )
            )

    def _on_notification(self, topic: str, data: dict[str, Any]) -> None:
        """Handle push notification from server."""
        payload = data.get("payload", data)
        if self._state.should_play_output():
            logger.info("Notification: %s", str(payload)[:100])
        else:
            self._state.queue_output(
                QueuedMessage(
                    content=json.dumps(payload),
                    priority=payload.get("priority", 2),
                    content_type="notification",
                )
            )

    def _on_mode_change(self, topic: str, data: dict[str, Any]) -> None:
        """Handle mode change command from server."""
        payload = data.get("payload", data)
        new_mode = payload.get("mode", "")

        if new_mode == "quiet":
            self._state.go_quiet()
        elif new_mode == "active":
            self._state.wake_up()
        elif new_mode == "sleep":
            self._state.go_to_sleep()
        elif new_mode == "morning":
            self._state.good_morning()

        self._publish_device_state()

    def _headphone_monitor_loop(self) -> None:
        """Background loop to monitor headphone connection."""
        while self._running:
            try:
                connected = self._headphone_monitor.check_connected()
                was_connected = self._state.headphones_connected

                if connected and not was_connected:
                    messages = self._state.on_headphones_connected()
                    if messages:
                        logger.info("Delivering %d queued messages", len(messages))
                    self._publish_device_state()
                elif not connected and was_connected:
                    self._state.on_headphones_disconnected()
                    self._publish_device_state()

            except Exception as e:
                logger.error("Headphone monitor error: %s", e)

            time.sleep(5)  # Check every 5 seconds

    def _publish_device_state(self) -> None:
        """Publish current device state to MQTT."""
        self._mqtt.publish(
            self._config.mqtt.topics.device_state,
            self._state.to_dict() | {"status": "online"},
            qos=0,
        )


def main() -> None:
    """Main entry point."""
    setup_logging(level="INFO", json_output=True)

    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    config = load_config(config_path)

    device = SottoEdgeDevice(config)

    # Handle graceful shutdown
    def signal_handler(sig: int, frame: Any) -> None:
        logger.info("Received signal %d, shutting down", sig)
        device.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        device.start()
    except KeyboardInterrupt:
        device.stop()
    except Exception as e:
        logger.error("Fatal error: %s", e)
        device.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
