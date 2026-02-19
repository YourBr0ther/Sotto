"""Audio output abstractions for Sotto edge device."""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioOutput(ABC):
    """Abstract audio output - swap implementations for different hardware."""

    @abstractmethod
    def play_audio(self, audio_data: bytes, sample_rate: int) -> None:
        """Play audio through the output device.

        Args:
            audio_data: Raw PCM audio bytes (16-bit signed, mono).
            sample_rate: Sample rate of the audio data.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if output device is connected and available."""


class SpeakerOutput(AudioOutput):
    """System speaker/headphone output using sounddevice.

    Routes audio to the system default output device, which could be
    Bluetooth headphones, built-in speaker, or USB audio.
    """

    def __init__(self, device_index: int | None = None) -> None:
        self._device_index = device_index

    def play_audio(self, audio_data: bytes, sample_rate: int) -> None:
        if not audio_data:
            logger.warning("Empty audio data, nothing to play")
            return

        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        audio_float = audio_array.astype(np.float32) / 32768.0

        try:
            sd.play(audio_float, samplerate=sample_rate, device=self._device_index)
            sd.wait()
            logger.debug("Played %d samples at %d Hz", len(audio_array), sample_rate)
        except sd.PortAudioError as e:
            logger.error("Failed to play audio: %s", e)
            raise

    def is_available(self) -> bool:
        try:
            devices = sd.query_devices()
            if self._device_index is not None:
                device = sd.query_devices(self._device_index)
                return device["max_output_channels"] > 0
            # Check default output
            default = sd.query_devices(kind="output")
            return default["max_output_channels"] > 0
        except (sd.PortAudioError, ValueError):
            return False


class HeadphoneMonitor:
    """Monitors Bluetooth headphone connection status.

    Uses platform-specific methods to detect headphone connection/disconnection.
    On Android (Termux), uses termux-audio-info.
    On Linux (Pi 5), uses bluetoothctl.
    """

    def __init__(self, platform: str = "android") -> None:
        self._platform = platform
        self._connected = False

    def check_connected(self) -> bool:
        """Check if Bluetooth headphones are currently connected.

        Returns:
            True if BT headphones are detected.
        """
        try:
            if self._platform == "android":
                return self._check_android()
            elif self._platform == "linux":
                return self._check_linux()
            else:
                logger.warning("Unknown platform %s, assuming no headphones", self._platform)
                return False
        except Exception as e:
            logger.error("Headphone check failed: %s", e)
            return self._connected  # Return last known state

    def _check_android(self) -> bool:
        """Check headphone connection on Android via Termux."""
        try:
            result = subprocess.run(
                ["termux-audio-info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # termux-audio-info returns JSON with Bluetooth info
            import json
            info = json.loads(result.stdout)
            connected = info.get("BLUETOOTH_A2DP_IS_ON", False)
            self._connected = connected
            return connected
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return self._connected

    def _check_linux(self) -> bool:
        """Check headphone connection on Linux via bluetoothctl."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            connected = "Connected: yes" in result.stdout
            self._connected = connected
            return connected
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return self._connected

    @property
    def last_known_state(self) -> bool:
        return self._connected
