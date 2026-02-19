"""Wake word detection for Sotto edge device."""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

WakeWordCallback = Callable[[], None]


class WakeWordDetector:
    """Wake word detection using OpenWakeWord.

    Listens to audio chunks and fires a callback when the wake word is detected.
    """

    def __init__(
        self,
        model_name: str = "hey_jarvis",
        threshold: float = 0.7,
        on_detected: WakeWordCallback | None = None,
    ) -> None:
        self._model_name = model_name
        self._threshold = threshold
        self._on_detected = on_detected
        self._model = None
        self._enabled = False

    def initialize(self) -> None:
        """Load the wake word model.

        Raises:
            ImportError: If openwakeword is not installed.
            RuntimeError: If the model fails to load.
        """
        try:
            from openwakeword.model import Model
            self._model = Model(wakeword_models=[self._model_name])
            self._enabled = True
            logger.info("Wake word model loaded: %s (threshold=%.2f)", self._model_name, self._threshold)
        except ImportError:
            logger.error("openwakeword not installed. Wake word detection unavailable.")
            raise
        except Exception as e:
            logger.error("Failed to load wake word model: %s", e)
            raise RuntimeError(f"Wake word model load failed: {e}") from e

    def process_audio(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """Process an audio chunk for wake word detection.

        Args:
            audio_chunk: Raw PCM audio bytes (16-bit signed, mono).
            sample_rate: Sample rate of the audio.

        Returns:
            True if wake word was detected in this chunk.
        """
        if not self._enabled or self._model is None:
            return False

        audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
        prediction = self._model.predict(audio_array)

        # Check all model scores
        for model_name, scores in prediction.items():
            if isinstance(scores, (list, np.ndarray)):
                max_score = max(scores) if len(scores) > 0 else 0
            else:
                max_score = scores

            if max_score >= self._threshold:
                logger.info("Wake word detected! (model=%s, score=%.3f)", model_name, max_score)
                if self._on_detected:
                    self._on_detected()
                return True

        return False

    def set_callback(self, callback: WakeWordCallback) -> None:
        """Set or update the wake word detection callback."""
        self._on_detected = callback

    def set_threshold(self, threshold: float) -> None:
        """Update the detection threshold."""
        self._threshold = threshold
        logger.info("Wake word threshold updated to %.2f", threshold)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def disable(self) -> None:
        """Temporarily disable wake word detection."""
        self._enabled = False

    def enable(self) -> None:
        """Re-enable wake word detection (model must already be loaded)."""
        if self._model is not None:
            self._enabled = True
