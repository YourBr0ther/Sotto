"""Tests for the audio streamer."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from audio.noise_filter import NoiseFilter
from comms.audio_streamer import AudioStreamer
from comms.mqtt_client import MqttClient


@pytest.fixture
def mock_mqtt() -> MagicMock:
    return MagicMock(spec=MqttClient)


@pytest.fixture
def noise_filter() -> NoiseFilter:
    return NoiseFilter()


@pytest.fixture
def streamer(mock_mqtt: MagicMock, noise_filter: NoiseFilter) -> AudioStreamer:
    return AudioStreamer(mock_mqtt, noise_filter)


class TestAudioStreamer:
    def test_stream_chunk_publishes_to_mqtt(self, streamer: AudioStreamer, mock_mqtt: MagicMock) -> None:
        audio = np.zeros(1600, dtype=np.int16).tobytes()
        streamer.stream_chunk(audio)
        mock_mqtt.publish.assert_called_once()

    def test_stream_chunk_returns_metadata(self, streamer: AudioStreamer) -> None:
        audio = np.random.randint(-5000, 5000, 1600, dtype=np.int16).tobytes()
        result = streamer.stream_chunk(audio)
        assert "quality_score" in result
        assert "chunk_index" in result
        assert "duration_ms" in result
        assert "size_bytes" in result

    def test_chunk_index_increments(self, streamer: AudioStreamer) -> None:
        audio = np.zeros(800, dtype=np.int16).tobytes()
        r1 = streamer.stream_chunk(audio)
        r2 = streamer.stream_chunk(audio)
        assert r1["chunk_index"] == 0
        assert r2["chunk_index"] == 1
        assert streamer.chunks_sent == 2

    def test_reset_counter(self, streamer: AudioStreamer) -> None:
        audio = np.zeros(800, dtype=np.int16).tobytes()
        streamer.stream_chunk(audio)
        streamer.reset_counter()
        assert streamer.chunks_sent == 0

    def test_payload_contains_base64_audio(self, streamer: AudioStreamer, mock_mqtt: MagicMock) -> None:
        audio = np.ones(800, dtype=np.int16).tobytes()
        streamer.stream_chunk(audio)

        call_args = mock_mqtt.publish.call_args
        payload = call_args[0][1]
        assert "audio_b64" in payload
        assert "sample_rate" in payload
        assert payload["sample_rate"] == 16000
        assert payload["encoding"] == "pcm_s16le"

    def test_uses_correct_topic(self, mock_mqtt: MagicMock, noise_filter: NoiseFilter) -> None:
        streamer = AudioStreamer(mock_mqtt, noise_filter, topic="sotto/custom/topic")
        audio = np.zeros(800, dtype=np.int16).tobytes()
        streamer.stream_chunk(audio)
        assert mock_mqtt.publish.call_args[0][0] == "sotto/custom/topic"
