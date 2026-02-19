"""Noise filtering for Sotto edge device audio."""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class NoiseFilter:
    """Basic noise reduction for audio input.

    Uses spectral gating to reduce background noise. For Phase 1,
    this provides a simple but effective noise floor reduction.
    """

    def __init__(self, sample_rate: int = 16000, noise_reduce_strength: float = 1.0) -> None:
        self._sample_rate = sample_rate
        self._strength = noise_reduce_strength
        self._noise_profile: np.ndarray | None = None
        self._enabled = True

    def filter_chunk(self, audio_chunk: bytes) -> bytes:
        """Apply noise reduction to an audio chunk.

        Args:
            audio_chunk: Raw PCM audio bytes (16-bit signed, mono).

        Returns:
            Filtered audio bytes in the same format.
        """
        if not self._enabled or len(audio_chunk) == 0:
            return audio_chunk

        audio = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)

        # Simple spectral gating
        filtered = self._spectral_gate(audio)

        # Clip to int16 range and convert back
        filtered = np.clip(filtered, -32768, 32767).astype(np.int16)
        return filtered.tobytes()

    def calibrate_noise_floor(self, ambient_audio: bytes) -> None:
        """Calibrate the noise profile from a sample of ambient noise.

        Args:
            ambient_audio: A few seconds of ambient audio for profiling.
        """
        audio = np.frombuffer(ambient_audio, dtype=np.int16).astype(np.float32)
        # Compute the noise spectrum
        fft = np.fft.rfft(audio)
        self._noise_profile = np.abs(fft)
        logger.info("Noise floor calibrated from %d samples", len(audio))

    def _spectral_gate(self, audio: np.ndarray) -> np.ndarray:
        """Apply spectral gating noise reduction."""
        if len(audio) == 0:
            return audio

        fft = np.fft.rfft(audio)
        magnitude = np.abs(fft)
        phase = np.angle(fft)

        if self._noise_profile is not None:
            # Subtract noise profile scaled by strength
            noise = self._noise_profile
            if len(noise) != len(magnitude):
                # Resize noise profile to match
                noise = np.interp(
                    np.linspace(0, 1, len(magnitude)),
                    np.linspace(0, 1, len(noise)),
                    noise,
                )
            magnitude = np.maximum(magnitude - noise * self._strength, 0)
        else:
            # Without calibration, apply a simple noise gate
            threshold = np.mean(magnitude) * 0.1
            magnitude = np.where(magnitude > threshold, magnitude, magnitude * 0.1)

        # Reconstruct signal
        filtered_fft = magnitude * np.exp(1j * phase)
        return np.fft.irfft(filtered_fft, n=len(audio))

    def compute_audio_quality(self, audio_chunk: bytes) -> float:
        """Compute a quality score for an audio chunk.

        Returns:
            Score between 0.0 (silent/noise) and 1.0 (clear speech).
        """
        if len(audio_chunk) == 0:
            return 0.0

        audio = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)

        # RMS energy
        rms = np.sqrt(np.mean(audio ** 2))

        # Normalize to a 0-1 scale (assuming int16 range)
        # Typical speech RMS is around 1000-5000 for int16
        quality = min(rms / 3000.0, 1.0)

        return round(quality, 3)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False
