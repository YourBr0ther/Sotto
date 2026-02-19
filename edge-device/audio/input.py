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
    """Microphone input using PulseAudio on Android/Termux.

    Android won't grant mic access to PulseAudio directly. The trick is to
    trigger the permission via termux-microphone-record first, then load
    PulseAudio's module-sles-source which taps into Android's audio subsystem.
    We then stream raw PCM continuously via parec — no clip gaps or ffmpeg.

    Requires: pkg install pulseaudio termux-api
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._capturing = False
        self._buffer: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self._reader_thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None

    def start_capture(self) -> None:
        if self._capturing:
            logger.warning("Audio capture already active")
            return

        # Step 1: Trigger Android mic permission via Termux:API
        logger.info("Triggering mic permission via termux-microphone-record")
        tmp_file = os.path.join(tempfile.gettempdir(), "sotto_mic_trigger.m4a")
        subprocess.run(
            ["termux-microphone-record", "-f", tmp_file, "-l", "1", "-c", "1"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(1.5)
        subprocess.run(
            ["termux-microphone-record", "-q"],
            capture_output=True,
            timeout=3,
        )
        # Clean up trigger file
        if os.path.exists(tmp_file):
            os.unlink(tmp_file)

        # Step 2: Start PulseAudio and load SLES source for Android mic
        logger.info("Starting PulseAudio with module-sles-source")
        subprocess.run(
            ["pulseaudio", "--start", "--exit-idle-time=-1"],
            capture_output=True,
        )
        subprocess.run(
            ["pactl", "load-module", "module-sles-source"],
            capture_output=True,
        )

        # Step 3: Start parec streaming raw PCM to stdout
        self._process = subprocess.Popen(
            [
                "parec",
                "--format=s16le",
                f"--rate={self._sample_rate}",
                "--channels=1",
                "--raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        self._capturing = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        logger.info("Termux PulseAudio mic capture started (rate=%d)", self._sample_rate)

    def _read_loop(self) -> None:
        """Background thread that reads raw PCM from parec stdout."""
        chunk_bytes = int(self._sample_rate * 0.1) * 2  # 100ms of 16-bit mono

        while self._capturing and self._process and self._process.stdout:
            try:
                data = self._process.stdout.read(chunk_bytes)
                if not data:
                    break
                try:
                    self._buffer.put_nowait(data)
                except queue.Full:
                    try:
                        self._buffer.get_nowait()
                        self._buffer.put_nowait(data)
                    except queue.Empty:
                        pass
            except Exception as e:
                logger.error("parec read error: %s", e)
                break

        if self._capturing:
            logger.warning("parec stream ended unexpectedly")

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

        # Kill parec process
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

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
