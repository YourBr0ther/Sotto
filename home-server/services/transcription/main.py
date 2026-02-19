"""Transcription service - MQTT subscriber that processes audio chunks."""

from __future__ import annotations

import base64
import json
import logging
import os
import signal
import sys
import time
from typing import Any

import paho.mqtt.client as mqtt

from whisper_engine import WhisperEngine

logger = logging.getLogger(__name__)


class TranscriptionService:
    """MQTT-connected transcription service.

    Subscribes to audio chunks from edge devices, transcribes them,
    and publishes the transcription results.
    """

    def __init__(
        self,
        mqtt_host: str = "localhost",
        mqtt_port: int = 1883,
        whisper_model: str = "base",
        whisper_device: str = "auto",
    ) -> None:
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._engine = WhisperEngine(
            model_size=whisper_model,
            device=whisper_device,
        )
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="sotto-transcription",
        )
        self._running = False
        self._audio_buffer: list[bytes] = []
        self._buffer_duration_ms = 0
        self._min_buffer_ms = 3000  # Accumulate at least 3s before transcribing

    def start(self) -> None:
        """Start the transcription service."""
        logger.info("Starting transcription service")

        # Initialize Whisper
        self._engine.initialize()

        # Setup MQTT
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self._mqtt_host, self._mqtt_port)

        self._running = True
        self._client.loop_forever()

    def stop(self) -> None:
        """Stop the transcription service."""
        self._running = False
        self._client.disconnect()
        logger.info("Transcription service stopped")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        logger.info("Connected to MQTT broker")
        self._client.subscribe("sotto/audio/raw", qos=0)

    def _on_message(self, client: Any, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            data = json.loads(message.payload.decode("utf-8"))
            payload = data.get("payload", {})

            audio_b64 = payload.get("audio_b64", "")
            if not audio_b64:
                return

            audio_bytes = base64.b64decode(audio_b64)
            duration_ms = payload.get("duration_ms", 0)

            self._audio_buffer.append(audio_bytes)
            self._buffer_duration_ms += duration_ms

            # Transcribe when we have enough audio
            if self._buffer_duration_ms >= self._min_buffer_ms:
                self._process_buffer(data.get("source", "unknown"))

        except Exception as e:
            logger.error("Error processing audio message: %s", e)

    def _process_buffer(self, source: str) -> None:
        """Transcribe accumulated audio buffer."""
        if not self._audio_buffer:
            return

        combined = b"".join(self._audio_buffer)
        self._audio_buffer.clear()
        self._buffer_duration_ms = 0

        try:
            result = self._engine.transcribe(combined)

            if result.text.strip():
                logger.info("Transcription: %s (conf=%.2f)", result.text[:100], result.confidence)

                # Publish transcription result
                self._client.publish(
                    "sotto/audio/transcription",
                    json.dumps({
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "source": source,
                        "type": "transcription",
                        "payload": {
                            "text": result.text,
                            "language": result.language,
                            "confidence": result.confidence,
                            "duration_seconds": result.duration_seconds,
                            "segments": result.segments,
                        },
                    }),
                    qos=1,
                )
        except Exception as e:
            logger.error("Transcription failed: %s", e)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    service = TranscriptionService(
        mqtt_host=os.environ.get("MQTT_HOST", "localhost"),
        mqtt_port=int(os.environ.get("MQTT_PORT", "1883")),
        whisper_model=os.environ.get("WHISPER_MODEL", "base"),
        whisper_device=os.environ.get("WHISPER_DEVICE", "auto"),
    )

    def signal_handler(sig: int, frame: Any) -> None:
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    service.start()


if __name__ == "__main__":
    main()
