"""Whisper speech-to-text engine for Sotto."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of a transcription."""

    text: str
    language: str
    confidence: float
    segments: list[dict[str, Any]]
    duration_seconds: float


class WhisperEngine:
    """Speech-to-text using faster-whisper.

    Wraps the faster-whisper library for efficient local transcription.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def initialize(self) -> None:
        """Load the Whisper model.

        Raises:
            ImportError: If faster-whisper is not installed.
            RuntimeError: If model loading fails.
        """
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            logger.info(
                "Whisper model loaded: %s (device=%s, compute=%s)",
                self._model_size,
                self._device,
                self._compute_type,
            )
        except ImportError:
            logger.error("faster-whisper not installed")
            raise
        except Exception as e:
            logger.error("Failed to load Whisper model: %s", e)
            raise RuntimeError(f"Whisper model load failed: {e}") from e

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> TranscriptionResult:
        """Transcribe audio data to text.

        Args:
            audio_data: Raw PCM audio bytes (16-bit signed, mono).
            sample_rate: Sample rate of the audio data.

        Returns:
            TranscriptionResult with text, language, confidence, and segments.

        Raises:
            RuntimeError: If the model is not loaded.
        """
        if self._model is None:
            raise RuntimeError("Whisper model not initialized. Call initialize() first.")

        # Convert bytes to float32 numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        segments_iter, info = self._model.transcribe(
            audio_array,
            beam_size=5,
            language=None,  # Auto-detect
            vad_filter=True,
            vad_parameters={"threshold": 0.1},
        )

        segments = []
        full_text_parts = []
        total_confidence = 0
        segment_count = 0

        for segment in segments_iter:
            segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "avg_logprob": segment.avg_logprob,
            })
            full_text_parts.append(segment.text)
            total_confidence += segment.avg_logprob
            segment_count += 1

        full_text = " ".join(full_text_parts).strip()
        avg_confidence = (total_confidence / segment_count) if segment_count > 0 else 0
        # Convert log prob to a 0-1 scale (rough approximation)
        confidence_score = min(max(1.0 + avg_confidence, 0.0), 1.0)

        duration = len(audio_array) / sample_rate

        return TranscriptionResult(
            text=full_text,
            language=info.language if info else "unknown",
            confidence=round(confidence_score, 3),
            segments=segments,
            duration_seconds=round(duration, 2),
        )

    def transcribe_file(self, file_path: str) -> TranscriptionResult:
        """Transcribe an audio file.

        Args:
            file_path: Path to the audio file.

        Returns:
            TranscriptionResult.
        """
        if self._model is None:
            raise RuntimeError("Whisper model not initialized")

        segments_iter, info = self._model.transcribe(
            file_path,
            beam_size=5,
            vad_filter=True,
        )

        segments = []
        full_text_parts = []

        for segment in segments_iter:
            segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            })
            full_text_parts.append(segment.text)

        return TranscriptionResult(
            text=" ".join(full_text_parts).strip(),
            language=info.language if info else "unknown",
            confidence=0.0,
            segments=segments,
            duration_seconds=0.0,
        )
