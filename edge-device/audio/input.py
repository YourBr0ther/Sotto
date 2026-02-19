"""Audio input abstractions for Sotto edge device."""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod

import numpy as np

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
    Falls back to TermuxMicInput on Android if sounddevice fails.
    """

    def __init__(self, device_index: int | None = None, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._device_index = device_index
        self._buffer: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)
        self._stream = None
        self._capturing = False

    def start_capture(self) -> None:
        import sounddevice as sd

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
        status: object,
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


class TermuxMicInput(AudioInput):
    """Microphone input using termux-microphone-record + ffmpeg on Android.

    PulseAudio can't access the Android mic in Termux, so we record short
    audio clips via the Termux:API, convert them to raw PCM with ffmpeg,
    and buffer the result for the main audio loop.

    Requires: pkg install termux-api ffmpeg
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._capturing = False
        self._buffer: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self._capture_thread: threading.Thread | None = None
        self._clip_dir = tempfile.mkdtemp(prefix="sotto_")

    def start_capture(self) -> None:
        if self._capturing:
            logger.warning("Audio capture already active")
            return

        self._capturing = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        logger.info("Termux mic capture started (rate=%d)", self._sample_rate)

    def _capture_loop(self) -> None:
        """Background thread: record short clips and convert to raw PCM."""
        clip_path = os.path.join(self._clip_dir, "clip.m4a")
        record_seconds = 2

        while self._capturing:
            try:
                # Remove previous clip
                if os.path.exists(clip_path):
                    os.unlink(clip_path)

                # Start recording via Termux:API (returns immediately)
                subprocess.run(
                    [
                        "termux-microphone-record",
                        "-f", clip_path,
                        "-l", str(record_seconds),
                        "-r", str(self._sample_rate),
                        "-c", "1",
                    ],
                    capture_output=True,
                    timeout=5,
                )

                # Wait for the recording to complete
                time.sleep(record_seconds + 0.5)

                # Ensure recording is stopped
                subprocess.run(
                    ["termux-microphone-record", "-q"],
                    capture_output=True,
                    timeout=3,
                )

                # Check the clip file exists and has content
                if not os.path.exists(clip_path) or os.path.getsize(clip_path) < 100:
                    logger.debug("No audio clip produced, retrying")
                    continue

                # Convert to raw PCM with ffmpeg
                result = subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", clip_path,
                        "-f", "s16le",
                        "-ar", str(self._sample_rate),
                        "-ac", "1",
                        "-loglevel", "error",
                        "pipe:1",
                    ],
                    capture_output=True,
                    timeout=10,
                )

                if result.returncode != 0:
                    stderr = result.stderr.decode(errors="replace")[:200]
                    logger.warning("ffmpeg convert failed: %s", stderr)
                    continue

                if not result.stdout:
                    continue

                # Split into 100ms chunks and push to buffer
                chunk_size = int(self._sample_rate * 0.1) * 2  # 100ms of 16-bit mono
                pcm = result.stdout
                for i in range(0, len(pcm) - chunk_size + 1, chunk_size):
                    piece = pcm[i : i + chunk_size]
                    try:
                        self._buffer.put_nowait(piece)
                    except queue.Full:
                        try:
                            self._buffer.get_nowait()
                            self._buffer.put_nowait(piece)
                        except queue.Empty:
                            pass

            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["termux-microphone-record", "-q"],
                    capture_output=True,
                )
                logger.warning("Recording timed out, retrying")
            except Exception as e:
                logger.error("Termux capture error: %s", e)
                time.sleep(1)

    def read_chunk(self, duration_ms: int = 500) -> bytes:
        if not self._capturing:
            raise RuntimeError("Audio capture not started")

        num_bytes = int(self._sample_rate * duration_ms / 1000) * 2  # 16-bit = 2 bytes
        collected = b""

        deadline = time.time() + (duration_ms / 1000) + 1.0
        while len(collected) < num_bytes and time.time() < deadline:
            try:
                block = self._buffer.get(timeout=0.1)
                collected += block
            except queue.Empty:
                continue

        # Trim to exact size
        if len(collected) > num_bytes:
            collected = collected[:num_bytes]

        return collected

    def stop_capture(self) -> None:
        self._capturing = False

        # Stop any active recording
        subprocess.run(
            ["termux-microphone-record", "-q"],
            capture_output=True,
        )

        # Drain buffer
        while not self._buffer.empty():
            try:
                self._buffer.get_nowait()
            except queue.Empty:
                break

        # Clean up temp directory
        import shutil
        shutil.rmtree(self._clip_dir, ignore_errors=True)

        logger.info("Termux audio capture stopped")

    def get_sample_rate(self) -> int:
        return self._sample_rate

    def is_capturing(self) -> bool:
        return self._capturing
