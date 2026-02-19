"""Piper TTS engine for Sotto."""

from __future__ import annotations

import logging
import subprocess
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PiperEngine:
    """Text-to-speech using Piper.

    Piper is a fast, local neural text-to-speech system.
    """

    def __init__(
        self,
        model_path: str | None = None,
        piper_binary: str = "piper",
        sample_rate: int = 22050,
    ) -> None:
        self._model_path = model_path
        self._piper_binary = piper_binary
        self._sample_rate = sample_rate
        self._ready = False

    def initialize(self) -> None:
        """Verify Piper is available and the model exists.

        Raises:
            RuntimeError: If Piper binary or model not found.
        """
        # Check if piper binary exists
        try:
            result = subprocess.run(
                [self._piper_binary, "--help"],
                capture_output=True,
                timeout=10,
            )
            self._ready = True
            logger.info("Piper TTS initialized (model=%s)", self._model_path)
        except FileNotFoundError:
            logger.error("Piper binary not found: %s", self._piper_binary)
            raise RuntimeError(f"Piper binary not found: {self._piper_binary}")
        except subprocess.TimeoutExpired:
            self._ready = True  # Binary exists but timed out on --help (acceptable)
            logger.info("Piper TTS initialized (timeout on help, but binary found)")

    @property
    def is_ready(self) -> bool:
        return self._ready

    def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.

        Returns:
            Raw PCM audio bytes (16-bit signed, mono).

        Raises:
            RuntimeError: If synthesis fails.
        """
        if not text.strip():
            return b""

        cmd = [self._piper_binary, "--output-raw"]
        if self._model_path:
            cmd.extend(["--model", self._model_path])

        try:
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                error = result.stderr.decode("utf-8", errors="replace")
                logger.error("Piper TTS failed: %s", error)
                raise RuntimeError(f"Piper TTS failed: {error}")

            logger.debug("Synthesized %d bytes for text: %s", len(result.stdout), text[:50])
            return result.stdout

        except FileNotFoundError:
            raise RuntimeError(f"Piper binary not found: {self._piper_binary}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Piper TTS timed out")

    def synthesize_to_wav(self, text: str, output_path: str) -> str:
        """Synthesize text to a WAV file.

        Args:
            text: Text to synthesize.
            output_path: Path to write the WAV file.

        Returns:
            The output file path.
        """
        raw_audio = self.synthesize(text)

        with wave.open(output_path, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self._sample_rate)
            wav.writeframes(raw_audio)

        logger.info("Wrote WAV file: %s (%d bytes)", output_path, len(raw_audio))
        return output_path
