"""Content classifier for public/private content routing."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from llm_client import OllamaClient

logger = logging.getLogger(__name__)

CLASSIFICATION_SYSTEM_PROMPT = """You are a content classifier for an ambient AI assistant.
Your job is to classify transcribed audio content as PUBLIC or PRIVATE.

Rules:
- PUBLIC: Work conversations, family logistics, tasks, appointments, meals, travel planning,
  general interests, media discussions, health/fitness, home management, shopping, errands.
- PRIVATE: Adult content, intimate conversations, personal preferences the user would not
  want spoken aloud, anything explicitly asked to keep private.

When in doubt, classify as PRIVATE. User privacy is always the priority.

Respond with ONLY a JSON object:
{"classification": "PUBLIC" or "PRIVATE", "confidence": 0.0-1.0, "reason": "brief reason"}"""


@dataclass
class ClassificationResult:
    """Result of content classification."""

    classification: str  # "PUBLIC" or "PRIVATE"
    confidence: float
    reason: str


class ContentClassifier:
    """Classifies content as public or private using the LLM."""

    def __init__(self, llm_client: OllamaClient) -> None:
        self._llm = llm_client

    def classify(self, text: str) -> ClassificationResult:
        """Classify text content as public or private.

        Args:
            text: The transcribed text to classify.

        Returns:
            ClassificationResult with classification and confidence.
        """
        if not text.strip():
            return ClassificationResult(
                classification="PUBLIC",
                confidence=1.0,
                reason="Empty content",
            )

        try:
            response = self._llm.generate(
                prompt=f"Classify this transcribed audio content:\n\n{text}",
                system=CLASSIFICATION_SYSTEM_PROMPT,
                temperature=0.1,
            )

            return self._parse_response(response.text)

        except (ConnectionError, RuntimeError) as e:
            logger.error("Classification failed, defaulting to PRIVATE: %s", e)
            return ClassificationResult(
                classification="PRIVATE",
                confidence=0.0,
                reason=f"Classification failed: {e}",
            )

    def _parse_response(self, response_text: str) -> ClassificationResult:
        """Parse the LLM's classification response."""
        try:
            # Try to extract JSON from the response
            text = response_text.strip()
            # Handle cases where LLM wraps in markdown code blocks
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)
            classification = data.get("classification", "PRIVATE").upper()

            if classification not in ("PUBLIC", "PRIVATE"):
                classification = "PRIVATE"

            return ClassificationResult(
                classification=classification,
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Failed to parse classification response: %s", e)
            # If we can't parse, check for keywords
            upper = response_text.upper()
            if "PUBLIC" in upper and "PRIVATE" not in upper:
                return ClassificationResult("PUBLIC", 0.5, "Keyword match")
            return ClassificationResult("PRIVATE", 0.3, "Parse failed, defaulting to private")
