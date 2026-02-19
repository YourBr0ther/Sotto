"""Tests for the content classifier."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from classifier import ClassificationResult, ContentClassifier
from llm_client import LLMResponse, OllamaClient


def _make_llm_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, model="test", tokens_used=10, done=True)


class TestClassificationResult:
    def test_fields(self) -> None:
        r = ClassificationResult(classification="PUBLIC", confidence=0.9, reason="Work talk")
        assert r.classification == "PUBLIC"
        assert r.confidence == 0.9
        assert r.reason == "Work talk"


class TestContentClassifierEmpty:
    def test_empty_string(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        classifier = ContentClassifier(llm)
        result = classifier.classify("")
        assert result.classification == "PUBLIC"
        assert result.confidence == 1.0
        llm.generate.assert_not_called()

    def test_whitespace_only(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        classifier = ContentClassifier(llm)
        result = classifier.classify("   \n  ")
        assert result.classification == "PUBLIC"
        llm.generate.assert_not_called()


class TestContentClassifierPublic:
    def test_public_classification(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            '{"classification": "PUBLIC", "confidence": 0.95, "reason": "Work meeting"}'
        )

        classifier = ContentClassifier(llm)
        result = classifier.classify("Let's schedule a meeting for Tuesday")

        assert result.classification == "PUBLIC"
        assert result.confidence == 0.95
        assert result.reason == "Work meeting"

    def test_public_with_code_block(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            '```json\n{"classification": "PUBLIC", "confidence": 0.9, "reason": "Shopping"}\n```'
        )

        classifier = ContentClassifier(llm)
        result = classifier.classify("I need to buy groceries")

        assert result.classification == "PUBLIC"
        assert result.confidence == 0.9


class TestContentClassifierPrivate:
    def test_private_classification(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            '{"classification": "PRIVATE", "confidence": 0.85, "reason": "Personal"}'
        )

        classifier = ContentClassifier(llm)
        result = classifier.classify("Some private conversation")
        assert result.classification == "PRIVATE"

    def test_invalid_classification_defaults_private(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            '{"classification": "UNKNOWN", "confidence": 0.5, "reason": "Unclear"}'
        )

        classifier = ContentClassifier(llm)
        result = classifier.classify("ambiguous content")
        assert result.classification == "PRIVATE"


class TestContentClassifierErrors:
    def test_connection_error_defaults_private(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.side_effect = ConnectionError("refused")

        classifier = ContentClassifier(llm)
        result = classifier.classify("some text")

        assert result.classification == "PRIVATE"
        assert result.confidence == 0.0

    def test_runtime_error_defaults_private(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.side_effect = RuntimeError("timeout")

        classifier = ContentClassifier(llm)
        result = classifier.classify("some text")

        assert result.classification == "PRIVATE"
        assert result.confidence == 0.0

    def test_malformed_json_keyword_public(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            "I think this is PUBLIC content because it's about work."
        )

        classifier = ContentClassifier(llm)
        result = classifier.classify("meeting at 2pm")

        assert result.classification == "PUBLIC"
        assert result.confidence == 0.5

    def test_malformed_json_keyword_private(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            "This contains PRIVATE information."
        )

        classifier = ContentClassifier(llm)
        result = classifier.classify("personal stuff")

        assert result.classification == "PRIVATE"

    def test_malformed_json_both_keywords(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            "Could be PUBLIC or PRIVATE, hard to tell."
        )

        classifier = ContentClassifier(llm)
        result = classifier.classify("ambiguous")

        # When both keywords present, defaults to PRIVATE
        assert result.classification == "PRIVATE"

    def test_malformed_json_no_keywords(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response("I have no idea.")

        classifier = ContentClassifier(llm)
        result = classifier.classify("something")

        assert result.classification == "PRIVATE"
        assert result.confidence == 0.3
