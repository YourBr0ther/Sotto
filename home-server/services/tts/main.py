"""TTS service - MQTT subscriber that generates speech from text."""

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

from piper_engine import PiperEngine

logger = logging.getLogger(__name__)


class TTSService:
    """MQTT-connected TTS service.

    Subscribes to text messages, synthesizes speech using Piper,
    and publishes the audio back for playback.
    """

    def __init__(
        self,
        mqtt_host: str = "localhost",
        mqtt_port: int = 1883,
        piper_model: str | None = None,
    ) -> None:
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._engine = PiperEngine(
            model_path=piper_model,
            piper_binary=os.environ.get("PIPER_BINARY", "piper"),
        )
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="sotto-tts",
        )
        self._running = False

    def start(self) -> None:
        """Start the TTS service."""
        logger.info("Starting TTS service")
        self._engine.initialize()

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self._mqtt_host, self._mqtt_port)

        self._running = True
        self._client.loop_forever()

    def stop(self) -> None:
        """Stop the TTS service."""
        self._running = False
        self._client.disconnect()
        logger.info("TTS service stopped")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        logger.info("Connected to MQTT broker")
        self._client.subscribe("sotto/audio/tts_text", qos=1)

    def _on_message(self, client: Any, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            data = json.loads(message.payload.decode("utf-8"))
            payload = data.get("payload", {})
            text = payload.get("text", "")

            if not text.strip():
                return

            logger.info("Synthesizing: %s", text[:80])
            audio_bytes = self._engine.synthesize(text)

            if audio_bytes:
                self._client.publish(
                    "sotto/audio/tts",
                    json.dumps({
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "source": "tts-service",
                        "type": "tts_audio",
                        "payload": {
                            "audio_b64": base64.b64encode(audio_bytes).decode("ascii"),
                            "sample_rate": 22050,
                            "text": text,
                            "encoding": "pcm_s16le",
                        },
                    }),
                    qos=1,
                )

        except Exception as e:
            logger.error("TTS processing error: %s", e)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    service = TTSService(
        mqtt_host=os.environ.get("MQTT_HOST", "localhost"),
        mqtt_port=int(os.environ.get("MQTT_PORT", "1883")),
        piper_model=os.environ.get("PIPER_MODEL"),
    )

    def signal_handler(sig: int, frame: Any) -> None:
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    service.start()


if __name__ == "__main__":
    main()
