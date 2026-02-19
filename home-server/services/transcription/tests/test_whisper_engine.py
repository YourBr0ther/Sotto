"""Tests for the Whisper transcription engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from whisper_engine import TranscriptionResult, WhisperEngine


class TestTranscriptionResult:
    def test_fields(self) -> None:
        r = TranscriptionResult(
            text="hello world",
            language="en",
            confidence=0.95,
            segments=[{"start": 0, "end": 1, "text": "hello world"}],
            duration_seconds=1.5,
        )
        assert r.text == "hello world"
        assert r.language == "en"
        assert r.confidence == 0.95
        assert len(r.segments) == 1
        assert r.duration_seconds == 1.5


class TestWhisperEngineInit:
    def test_defaults(self) -> None:
        engine = WhisperEngine()
        assert engine._model_size == "base"
        assert engine._device == "auto"
        assert engine._compute_type == "auto"
        assert engine._model is None
        assert engine.is_ready is False

    def test_custom_params(self) -> None:
        engine = WhisperEngine(model_size="large-v3", device="cuda", compute_type="float16")
        assert engine._model_size == "large-v3"
        assert engine._device == "cuda"
        assert engine._compute_type == "float16"


class TestWhisperEngineInitialize:
    @patch("whisper_engine.WhisperModel", create=True)
    def test_successful_init(self, mock_model_class: MagicMock) -> None:
        # We need to patch the import inside initialize
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model

        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=mock_model_class)}):
            engine = WhisperEngine()
            engine.initialize()
            assert engine.is_ready is True

    def test_not_ready_before_init(self) -> None:
        engine = WhisperEngine()
        assert engine.is_ready is False


class TestWhisperEngineTranscribe:
    def test_transcribe_not_initialized(self) -> None:
        engine = WhisperEngine()
        with pytest.raises(RuntimeError, match="not initialized"):
            engine.transcribe(b"\x00" * 100)

    def test_transcribe_success(self) -> None:
        engine = WhisperEngine()

        # Create mock model
        mock_model = MagicMock()
        engine._model = mock_model

        # Create mock segment
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 1.5
        mock_segment.text = "Hello world"
        mock_segment.avg_logprob = -0.2

        mock_info = MagicMock()
        mock_info.language = "en"

        mock_model.transcribe.return_value = (iter([mock_segment]), mock_info)

        # Create 1 second of silence (16-bit PCM, 16kHz)
        audio_data = np.zeros(16000, dtype=np.int16).tobytes()
        result = engine.transcribe(audio_data, sample_rate=16000)

        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.confidence > 0
        assert len(result.segments) == 1
        assert result.duration_seconds == 1.0

    def test_transcribe_empty_audio(self) -> None:
        engine = WhisperEngine()
        mock_model = MagicMock()
        engine._model = mock_model

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe.return_value = (iter([]), mock_info)

        audio_data = np.zeros(1600, dtype=np.int16).tobytes()
        result = engine.transcribe(audio_data)

        assert result.text == ""
        # With no segments, avg_logprob is 0, so confidence = min(max(1.0 + 0, 0), 1.0) = 1.0
        assert result.confidence == 1.0

    def test_transcribe_multiple_segments(self) -> None:
        engine = WhisperEngine()
        mock_model = MagicMock()
        engine._model = mock_model

        seg1 = MagicMock()
        seg1.start, seg1.end, seg1.text, seg1.avg_logprob = 0.0, 1.0, "First part", -0.1

        seg2 = MagicMock()
        seg2.start, seg2.end, seg2.text, seg2.avg_logprob = 1.0, 2.5, "second part", -0.3

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe.return_value = (iter([seg1, seg2]), mock_info)

        audio_data = np.zeros(32000, dtype=np.int16).tobytes()
        result = engine.transcribe(audio_data)

        assert "First part" in result.text
        assert "second part" in result.text
        assert len(result.segments) == 2


class TestWhisperEngineTranscribeFile:
    def test_transcribe_file_not_initialized(self) -> None:
        engine = WhisperEngine()
        with pytest.raises(RuntimeError, match="not initialized"):
            engine.transcribe_file("/fake/path.wav")

    def test_transcribe_file_success(self) -> None:
        engine = WhisperEngine()
        mock_model = MagicMock()
        engine._model = mock_model

        seg = MagicMock()
        seg.start, seg.end, seg.text = 0.0, 2.0, "File transcription"

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe.return_value = (iter([seg]), mock_info)

        result = engine.transcribe_file("/some/audio.wav")

        assert result.text == "File transcription"
        assert result.language == "en"
        assert len(result.segments) == 1
        mock_model.transcribe.assert_called_once_with(
            "/some/audio.wav",
            beam_size=5,
            vad_filter=True,
        )
