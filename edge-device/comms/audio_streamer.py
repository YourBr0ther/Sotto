"""Audio streaming to home server via MQTT."""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

from audio.noise_filter import NoiseFilter
from comms.mqtt_client import MqttClient

logger = logging.getLogger(__name__)


class AudioStreamer:
    """Streams audio chunks to the home server via MQTT.

    Handles chunking, encoding, quality scoring, and noise filtering
    before publishing audio data to the MQTT broker.
    """

    def __init__(
        self,
        mqtt_client: MqttClient,
        noise_filter: NoiseFilter,
        topic: str = "sotto/audio/raw",
        sample_rate: int = 16000,
    ) -> None:
        self._mqtt = mqtt_client
        self._noise_filter = noise_filter
        self._topic = topic
        self._sample_rate = sample_rate
        self._chunks_sent = 0
        self._streaming = False

    def stream_chunk(self, audio_chunk: bytes) -> dict[str, Any]:
        """Process and stream an audio chunk to the server.

        Args:
            audio_chunk: Raw PCM audio bytes (16-bit signed, mono).

        Returns:
            Dict with streaming metadata (quality_score, chunk_index, etc.)
        """
        # Apply noise filtering
        filtered = self._noise_filter.filter_chunk(audio_chunk)

        # Compute quality score
        quality = self._noise_filter.compute_audio_quality(filtered)

        # Encode for MQTT transport
        audio_b64 = base64.b64encode(filtered).decode("ascii")

        duration_ms = len(filtered) // (self._sample_rate * 2) * 1000  # 2 bytes per int16 sample
        if duration_ms == 0 and len(filtered) > 0:
            duration_ms = int(len(filtered) / (self._sample_rate * 2) * 1000)

        payload = {
            "audio_b64": audio_b64,
            "sample_rate": self._sample_rate,
            "duration_ms": duration_ms,
            "quality_score": quality,
            "chunk_index": self._chunks_sent,
            "encoding": "pcm_s16le",
        }

        self._mqtt.publish(self._topic, payload, qos=0)
        self._chunks_sent += 1

        return {
            "quality_score": quality,
            "chunk_index": self._chunks_sent - 1,
            "duration_ms": duration_ms,
            "size_bytes": len(filtered),
        }

    @property
    def chunks_sent(self) -> int:
        return self._chunks_sent

    def reset_counter(self) -> None:
        self._chunks_sent = 0
