"""Tests for the transcription MQTT service."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the transcription main module with a unique name to avoid collision
# with other services' main.py files
_service_dir = str(Path(__file__).parent.parent)
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)

_spec = importlib.util.spec_from_file_location(
    "transcription_main",
    str(Path(__file__).parent.parent / "main.py"),
)
transcription_main = importlib.util.module_from_spec(_spec)
sys.modules["transcription_main"] = transcription_main
_spec.loader.exec_module(transcription_main)

TranscriptionService = transcription_main.TranscriptionService

from whisper_engine import TranscriptionResult


class TestTranscriptionServiceInit:
    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_init_defaults(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService()
        assert svc._mqtt_host == "localhost"
        assert svc._mqtt_port == 1883
        assert svc._buffer_duration_ms == 0
        assert svc._audio_buffer == []

    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_init_custom(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService(
            mqtt_host="broker",
            mqtt_port=1884,
            whisper_model="large-v3",
            whisper_device="cuda",
        )
        assert svc._mqtt_host == "broker"
        assert svc._mqtt_port == 1884


class TestTranscriptionServiceOnConnect:
    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_subscribes_to_audio_raw(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService()
        svc._on_connect(None, None, None, 0)
        svc._client.subscribe.assert_called_once_with("sotto/audio/raw", qos=0)


class TestTranscriptionServiceOnMessage:
    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_buffers_audio(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService()
        svc._min_buffer_ms = 5000  # Set high so it just buffers

        audio = b"\x00\x01\x02\x03"
        msg = MagicMock()
        msg.payload = json.dumps({
            "source": "edge-1",
            "payload": {
                "audio_b64": base64.b64encode(audio).decode("ascii"),
                "duration_ms": 100,
            },
        }).encode("utf-8")

        svc._on_message(None, None, msg)

        assert len(svc._audio_buffer) == 1
        assert svc._buffer_duration_ms == 100

    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_ignores_empty_audio(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService()

        msg = MagicMock()
        msg.payload = json.dumps({
            "source": "edge-1",
            "payload": {"audio_b64": "", "duration_ms": 100},
        }).encode("utf-8")

        svc._on_message(None, None, msg)

        assert len(svc._audio_buffer) == 0

    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_triggers_processing_at_threshold(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService()
        svc._min_buffer_ms = 200

        # Mock the engine to return a result
        svc._engine.transcribe.return_value = TranscriptionResult(
            text="Hello",
            language="en",
            confidence=0.9,
            segments=[],
            duration_seconds=0.3,
        )

        audio = b"\x00" * 100
        msg = MagicMock()
        msg.payload = json.dumps({
            "source": "edge-1",
            "payload": {
                "audio_b64": base64.b64encode(audio).decode("ascii"),
                "duration_ms": 300,
            },
        }).encode("utf-8")

        svc._on_message(None, None, msg)

        # Buffer should be cleared after processing
        assert svc._audio_buffer == []
        assert svc._buffer_duration_ms == 0
        svc._engine.transcribe.assert_called_once()


class TestTranscriptionServiceProcessBuffer:
    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_publishes_transcription(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService()
        svc._audio_buffer = [b"\x00" * 100, b"\x01" * 100]
        svc._buffer_duration_ms = 3000

        svc._engine.transcribe.return_value = TranscriptionResult(
            text="Test transcription",
            language="en",
            confidence=0.85,
            segments=[{"start": 0, "end": 1, "text": "Test transcription"}],
            duration_seconds=3.0,
        )

        svc._process_buffer("edge-1")

        svc._client.publish.assert_called_once()
        call_args = svc._client.publish.call_args
        assert call_args[0][0] == "sotto/audio/transcription"

        published = json.loads(call_args[0][1])
        assert published["source"] == "edge-1"
        assert published["type"] == "transcription"
        assert published["payload"]["text"] == "Test transcription"
        assert published["payload"]["confidence"] == 0.85

    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_empty_buffer_noop(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService()
        svc._audio_buffer = []

        svc._process_buffer("edge-1")

        svc._engine.transcribe.assert_not_called()

    @patch("transcription_main.WhisperEngine")
    @patch("transcription_main.mqtt.Client")
    def test_empty_transcription_not_published(self, mock_mqtt: MagicMock, mock_whisper: MagicMock) -> None:
        svc = TranscriptionService()
        svc._audio_buffer = [b"\x00" * 100]
        svc._buffer_duration_ms = 3000

        svc._engine.transcribe.return_value = TranscriptionResult(
            text="   ",
            language="en",
            confidence=0.1,
            segments=[],
            duration_seconds=0.1,
        )

        svc._process_buffer("edge-1")
        svc._client.publish.assert_not_called()
