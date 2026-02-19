"""Tests for the Piper TTS engine."""

from __future__ import annotations

import os
import tempfile
import wave
from unittest.mock import MagicMock, patch

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from piper_engine import PiperEngine


class TestPiperEngineInit:
    def test_defaults(self) -> None:
        engine = PiperEngine()
        assert engine._model_path is None
        assert engine._piper_binary == "piper"
        assert engine._sample_rate == 22050
        assert engine.is_ready is False

    def test_custom_params(self) -> None:
        engine = PiperEngine(
            model_path="/models/en_US.onnx",
            piper_binary="/usr/local/bin/piper",
            sample_rate=16000,
        )
        assert engine._model_path == "/models/en_US.onnx"
        assert engine._piper_binary == "/usr/local/bin/piper"
        assert engine._sample_rate == 16000


class TestPiperEngineInitialize:
    @patch("piper_engine.subprocess.run")
    def test_successful_init(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)

        engine = PiperEngine()
        engine.initialize()
        assert engine.is_ready is True

        mock_run.assert_called_once_with(
            ["piper", "--help"],
            capture_output=True,
            timeout=10,
        )

    @patch("piper_engine.subprocess.run")
    def test_binary_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError()

        engine = PiperEngine()
        with pytest.raises(RuntimeError, match="not found"):
            engine.initialize()
        assert engine.is_ready is False

    @patch("piper_engine.subprocess.run")
    def test_timeout_still_ready(self, mock_run: MagicMock) -> None:
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="piper", timeout=10)

        engine = PiperEngine()
        engine.initialize()
        assert engine.is_ready is True


class TestPiperEngineSynthesize:
    @patch("piper_engine.subprocess.run")
    def test_synthesize_success(self, mock_run: MagicMock) -> None:
        fake_audio = b"\x00\x01" * 1000
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=fake_audio,
            stderr=b"",
        )

        engine = PiperEngine(model_path="/models/test.onnx")
        engine._ready = True
        result = engine.synthesize("Hello world")

        assert result == fake_audio
        cmd = mock_run.call_args[0][0]
        assert cmd == ["piper", "--output-raw", "--model", "/models/test.onnx"]
        assert mock_run.call_args[1]["input"] == b"Hello world"

    @patch("piper_engine.subprocess.run")
    def test_synthesize_no_model(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=b"\x00", stderr=b"")

        engine = PiperEngine()  # No model_path
        engine._ready = True
        engine.synthesize("Test")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["piper", "--output-raw"]
        assert "--model" not in cmd

    def test_synthesize_empty_text(self) -> None:
        engine = PiperEngine()
        engine._ready = True
        result = engine.synthesize("")
        assert result == b""

    def test_synthesize_whitespace_only(self) -> None:
        engine = PiperEngine()
        engine._ready = True
        result = engine.synthesize("   \n  ")
        assert result == b""

    @patch("piper_engine.subprocess.run")
    def test_synthesize_nonzero_return(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"Error: model not found",
        )

        engine = PiperEngine()
        engine._ready = True
        with pytest.raises(RuntimeError, match="Piper TTS failed"):
            engine.synthesize("Hello")

    @patch("piper_engine.subprocess.run")
    def test_synthesize_binary_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError()

        engine = PiperEngine()
        engine._ready = True
        with pytest.raises(RuntimeError, match="not found"):
            engine.synthesize("Hello")

    @patch("piper_engine.subprocess.run")
    def test_synthesize_timeout(self, mock_run: MagicMock) -> None:
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="piper", timeout=30)

        engine = PiperEngine()
        engine._ready = True
        with pytest.raises(RuntimeError, match="timed out"):
            engine.synthesize("Hello")


class TestPiperEngineSynthesizeToWav:
    @patch("piper_engine.subprocess.run")
    def test_writes_wav_file(self, mock_run: MagicMock) -> None:
        # 1 second of silence at 22050Hz, 16-bit mono
        fake_audio = b"\x00\x00" * 22050
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=fake_audio,
            stderr=b"",
        )

        engine = PiperEngine(sample_rate=22050)
        engine._ready = True

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name

        try:
            result = engine.synthesize_to_wav("Hello", output_path)
            assert result == output_path
            assert os.path.exists(output_path)

            with wave.open(output_path, "r") as wav:
                assert wav.getnchannels() == 1
                assert wav.getsampwidth() == 2
                assert wav.getframerate() == 22050
                assert wav.getnframes() == 22050
        finally:
            os.unlink(output_path)
