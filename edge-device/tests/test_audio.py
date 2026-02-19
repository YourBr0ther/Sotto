"""Tests for audio input, output, noise filter, and wake word modules."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from audio.input import AudioInput, PhoneMicInput
from audio.noise_filter import NoiseFilter
from audio.output import AudioOutput, HeadphoneMonitor, SpeakerOutput
from audio.wake_word import WakeWordDetector


# --- Audio Input Tests ---

class TestAudioInputABC:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            AudioInput()  # type: ignore


class TestPhoneMicInput:
    def test_init_defaults(self) -> None:
        with patch("audio.input.sd"):
            mic = PhoneMicInput()
            assert mic.get_sample_rate() == 16000
            assert mic.is_capturing() is False

    def test_init_custom_rate(self) -> None:
        with patch("audio.input.sd"):
            mic = PhoneMicInput(sample_rate=44100)
            assert mic.get_sample_rate() == 44100

    def test_start_capture(self) -> None:
        with patch("audio.input.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            mic = PhoneMicInput()
            mic.start_capture()

            assert mic.is_capturing() is True
            mock_stream.start.assert_called_once()

    def test_start_capture_twice_warns(self) -> None:
        with patch("audio.input.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            mic = PhoneMicInput()
            mic.start_capture()
            mic.start_capture()  # Should not create another stream

            assert mock_sd.InputStream.call_count == 1

    def test_stop_capture(self) -> None:
        with patch("audio.input.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            mic = PhoneMicInput()
            mic.start_capture()
            mic.stop_capture()

            assert mic.is_capturing() is False
            mock_stream.stop.assert_called_once()
            mock_stream.close.assert_called_once()

    def test_read_chunk_raises_when_not_capturing(self) -> None:
        with patch("audio.input.sd"):
            mic = PhoneMicInput()
            with pytest.raises(RuntimeError, match="not started"):
                mic.read_chunk()

    def test_read_chunk_returns_bytes(self) -> None:
        with patch("audio.input.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.InputStream.return_value = mock_stream

            mic = PhoneMicInput(sample_rate=16000)
            mic.start_capture()

            # Simulate audio data in buffer
            test_data = np.zeros(1600, dtype=np.int16).reshape(-1, 1)
            mic._buffer.put(test_data)

            chunk = mic.read_chunk(duration_ms=100)
            assert isinstance(chunk, bytes)
            assert len(chunk) > 0


# --- Audio Output Tests ---

class TestAudioOutputABC:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            AudioOutput()  # type: ignore


class TestSpeakerOutput:
    def test_play_empty_audio_warns(self) -> None:
        with patch("audio.output.sd"):
            output = SpeakerOutput()
            output.play_audio(b"", 16000)  # Should not raise

    def test_play_audio_calls_sounddevice(self) -> None:
        with patch("audio.output.sd") as mock_sd:
            output = SpeakerOutput()
            # Create some test audio
            audio = np.zeros(1600, dtype=np.int16).tobytes()
            output.play_audio(audio, 16000)
            mock_sd.play.assert_called_once()
            mock_sd.wait.assert_called_once()

    def test_is_available_checks_devices(self) -> None:
        with patch("audio.output.sd") as mock_sd:
            mock_sd.query_devices.return_value = {"max_output_channels": 2}
            output = SpeakerOutput()
            assert output.is_available() is True


# --- Headphone Monitor Tests ---

class TestHeadphoneMonitor:
    def test_init_not_connected(self) -> None:
        monitor = HeadphoneMonitor()
        assert monitor.last_known_state is False

    def test_android_check_calls_termux(self) -> None:
        monitor = HeadphoneMonitor(platform="android")
        with patch("audio.output.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"BLUETOOTH_A2DP_IS_ON": true}',
                returncode=0,
            )
            result = monitor.check_connected()
            assert result is True

    def test_android_check_handles_missing_termux(self) -> None:
        monitor = HeadphoneMonitor(platform="android")
        with patch("audio.output.subprocess.run", side_effect=FileNotFoundError):
            result = monitor.check_connected()
            assert result is False  # Falls back to last known

    def test_linux_check_calls_bluetoothctl(self) -> None:
        monitor = HeadphoneMonitor(platform="linux")
        with patch("audio.output.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Device XX:XX:XX\n\tConnected: yes\n",
                returncode=0,
            )
            result = monitor.check_connected()
            assert result is True

    def test_unknown_platform_returns_false(self) -> None:
        monitor = HeadphoneMonitor(platform="windows")
        result = monitor.check_connected()
        assert result is False


# --- Noise Filter Tests ---

class TestNoiseFilter:
    def test_filter_empty_audio(self) -> None:
        nf = NoiseFilter()
        result = nf.filter_chunk(b"")
        assert result == b""

    def test_filter_preserves_audio_length(self) -> None:
        nf = NoiseFilter()
        audio = np.random.randint(-1000, 1000, 1600, dtype=np.int16).tobytes()
        result = nf.filter_chunk(audio)
        assert len(result) == len(audio)

    def test_filter_returns_bytes(self) -> None:
        nf = NoiseFilter()
        audio = np.zeros(1600, dtype=np.int16).tobytes()
        result = nf.filter_chunk(audio)
        assert isinstance(result, bytes)

    def test_disabled_filter_passes_through(self) -> None:
        nf = NoiseFilter()
        nf.disable()
        audio = np.random.randint(-1000, 1000, 1600, dtype=np.int16).tobytes()
        result = nf.filter_chunk(audio)
        assert result == audio

    def test_enable_disable(self) -> None:
        nf = NoiseFilter()
        assert nf.is_enabled is True
        nf.disable()
        assert nf.is_enabled is False
        nf.enable()
        assert nf.is_enabled is True

    def test_calibrate_noise_floor(self) -> None:
        nf = NoiseFilter()
        noise = np.random.randint(-100, 100, 16000, dtype=np.int16).tobytes()
        nf.calibrate_noise_floor(noise)
        assert nf._noise_profile is not None

    def test_filter_with_calibration(self) -> None:
        nf = NoiseFilter()
        noise = np.random.randint(-100, 100, 16000, dtype=np.int16).tobytes()
        nf.calibrate_noise_floor(noise)

        audio = np.random.randint(-5000, 5000, 1600, dtype=np.int16).tobytes()
        result = nf.filter_chunk(audio)
        assert isinstance(result, bytes)
        assert len(result) == len(audio)

    def test_audio_quality_silent(self) -> None:
        nf = NoiseFilter()
        silent = np.zeros(1600, dtype=np.int16).tobytes()
        quality = nf.compute_audio_quality(silent)
        assert quality == 0.0

    def test_audio_quality_loud(self) -> None:
        nf = NoiseFilter()
        loud = np.full(1600, 10000, dtype=np.int16).tobytes()
        quality = nf.compute_audio_quality(loud)
        assert quality > 0.5

    def test_audio_quality_empty(self) -> None:
        nf = NoiseFilter()
        quality = nf.compute_audio_quality(b"")
        assert quality == 0.0

    def test_audio_quality_range(self) -> None:
        nf = NoiseFilter()
        audio = np.random.randint(-32768, 32767, 1600, dtype=np.int16).tobytes()
        quality = nf.compute_audio_quality(audio)
        assert 0.0 <= quality <= 1.0


# --- Wake Word Tests ---

class TestWakeWordDetector:
    def test_init_disabled_by_default(self) -> None:
        ww = WakeWordDetector()
        assert ww.is_enabled is False

    def test_process_audio_when_disabled_returns_false(self) -> None:
        ww = WakeWordDetector()
        audio = np.zeros(1600, dtype=np.int16).tobytes()
        assert ww.process_audio(audio) is False

    def test_set_callback(self) -> None:
        ww = WakeWordDetector()
        callback = MagicMock()
        ww.set_callback(callback)
        assert ww._on_detected == callback

    def test_set_threshold(self) -> None:
        ww = WakeWordDetector(threshold=0.5)
        ww.set_threshold(0.8)
        assert ww._threshold == 0.8

    def test_disable_enable(self) -> None:
        ww = WakeWordDetector()
        ww._model = MagicMock()  # Simulate loaded model
        ww._enabled = True

        ww.disable()
        assert ww.is_enabled is False

        ww.enable()
        assert ww.is_enabled is True

    def test_enable_without_model_stays_disabled(self) -> None:
        ww = WakeWordDetector()
        ww.enable()
        assert ww.is_enabled is False  # No model loaded

    def test_initialize_raises_without_openwakeword(self) -> None:
        ww = WakeWordDetector()
        with patch.dict("sys.modules", {"openwakeword": None, "openwakeword.model": None}):
            with pytest.raises((ImportError, RuntimeError)):
                ww.initialize()
