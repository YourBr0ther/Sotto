"""Audio input abstractions for Sotto edge device."""

from __future__ import annotations

import logging
import queue
import threading
from abc import ABC, abstractmethod

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioInput(ABC):
    """Abstract audio input - swap implementations for different hardware."""

    @abstractmethod
    def start_capture(self) -> None:
        """Begin continuous audio capture."""

    @abstractmethod
    def read_chunk(self, duration_ms: int = 500) -> bytes:
        """Read a chunk of audio data as raw PCM bytes.

        Args:
            duration_ms: Duration of the chunk in milliseconds.

        Returns:
            Raw PCM audio bytes (16-bit signed, mono).
        """

    @abstractmethod
    def stop_capture(self) -> None:
        """Stop audio capture."""

    @abstractmethod
    def get_sample_rate(self) -> int:
        """Return the sample rate of the audio stream."""

    @abstractmethod
    def is_capturing(self) -> bool:
        """Whether audio capture is currently active."""


class PhoneMicInput(AudioInput):
    """Phone microphone implementation using sounddevice.

    Captures audio from the system default microphone (or specified device).
    Audio is captured in a background thread and buffered for reading.
    """

    def __init__(self, device_index: int | None = None, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._device_index = device_index
        self._buffer: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)
        self._stream: sd.InputStream | None = None
        self._capturing = False

    def start_capture(self) -> None:
        if self._capturing:
            logger.warning("Audio capture already active")
            return

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            device=self._device_index,
            blocksize=int(self._sample_rate * 0.1),  # 100ms blocks
            callback=self._audio_callback,
        )
        self._stream.start()
        self._capturing = True
        logger.info("Audio capture started (rate=%d, device=%s)", self._sample_rate, self._device_index)

    def read_chunk(self, duration_ms: int = 500) -> bytes:
        if not self._capturing:
            raise RuntimeError("Audio capture not started")

        num_samples = int(self._sample_rate * duration_ms / 1000)
        collected = np.array([], dtype=np.int16)

        while len(collected) < num_samples:
            try:
                block = self._buffer.get(timeout=duration_ms / 1000 + 1.0)
                collected = np.concatenate([collected, block.flatten()])
            except queue.Empty:
                break

        # Trim to exact size
        if len(collected) > num_samples:
            collected = collected[:num_samples]

        return collected.tobytes()

    def stop_capture(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._capturing = False
        # Drain buffer
        while not self._buffer.empty():
            try:
                self._buffer.get_nowait()
            except queue.Empty:
                break
        logger.info("Audio capture stopped")

    def get_sample_rate(self) -> int:
        return self._sample_rate

    def is_capturing(self) -> bool:
        return self._capturing

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: dict,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback for sounddevice InputStream."""
        if status:
            logger.warning("Audio input status: %s", status)
        try:
            self._buffer.put_nowait(indata.copy())
        except queue.Full:
            # Drop oldest block to make room
            try:
                self._buffer.get_nowait()
                self._buffer.put_nowait(indata.copy())
            except queue.Empty:
                pass
