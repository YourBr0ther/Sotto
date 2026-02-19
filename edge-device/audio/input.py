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
    """Microphone input using Termux:API's termux-microphone-record.

    This works on Android where PortAudio/sounddevice cannot access the mic.
    Records to a temp file in the background and reads chunks from it.
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._capturing = False
        self._process: subprocess.Popen | None = None
        self._buffer: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self._reader_thread: threading.Thread | None = None
        self._tmp_file: str | None = None

    def start_capture(self) -> None:
        if self._capturing:
            logger.warning("Audio capture already active")
            return

        # Create a temp file for the raw PCM output
        fd, self._tmp_file = tempfile.mkstemp(suffix=".pcm")
        os.close(fd)

        # Start termux-microphone-record outputting raw PCM
        # -f raw: raw PCM, -r: sample rate, -c 1: mono, -e: 16-bit
        self._process = subprocess.Popen(
            [
                "termux-microphone-record",
                "-f", self._tmp_file,
                "-r", str(self._sample_rate),
                "-c", "1",
                "-e", "16",
                "-l", "0",  # record indefinitely
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Give it a moment to start
        time.sleep(0.5)

        # Start reader thread that reads from the file
        self._capturing = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        logger.info("Termux audio capture started (rate=%d)", self._sample_rate)

    def _read_loop(self) -> None:
        """Background thread that reads PCM data from the recording file."""
        chunk_bytes = int(self._sample_rate * 0.1) * 2  # 100ms of 16-bit mono
        read_pos = 0

        while self._capturing:
            try:
                if self._tmp_file and os.path.exists(self._tmp_file):
                    file_size = os.path.getsize(self._tmp_file)
                    if file_size > read_pos + chunk_bytes:
                        with open(self._tmp_file, "rb") as f:
                            f.seek(read_pos)
                            data = f.read(chunk_bytes)
                        if data:
                            read_pos += len(data)
                            try:
                                self._buffer.put_nowait(data)
                            except queue.Full:
                                try:
                                    self._buffer.get_nowait()
                                    self._buffer.put_nowait(data)
                                except queue.Empty:
                                    pass
                    else:
                        time.sleep(0.05)
                else:
                    time.sleep(0.1)
            except Exception as e:
                logger.error("Termux audio read error: %s", e)
                time.sleep(0.1)

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

        # Stop the recording
        try:
            subprocess.run(
                ["termux-microphone-record", "-q"],
                timeout=5,
                capture_output=True,
            )
        except Exception:
            pass

        if self._process is not None:
            self._process.terminate()
            self._process = None

        # Clean up temp file
        if self._tmp_file and os.path.exists(self._tmp_file):
            try:
                os.unlink(self._tmp_file)
            except OSError:
                pass
            self._tmp_file = None

        # Drain buffer
        while not self._buffer.empty():
            try:
                self._buffer.get_nowait()
            except queue.Empty:
                break

        logger.info("Termux audio capture stopped")

    def get_sample_rate(self) -> int:
        return self._sample_rate

    def is_capturing(self) -> bool:
        return self._capturing
