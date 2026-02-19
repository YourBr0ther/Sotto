"""Tests for the task extractor."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_client import LLMResponse, OllamaClient
from task_extractor import (
    ExtractionResult,
    ExtractedTask,
    IncompleteItem,
    TaskExtractor,
)


def _make_llm_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, model="test", tokens_used=10, done=True)


class TestExtractedTask:
    def test_defaults(self) -> None:
        task = ExtractedTask(description="Do something")
        assert task.description == "Do something"
        assert task.people == []
        assert task.due_date is None
        assert task.source_quote == ""
        assert task.urgency == "medium"


class TestExtractionResult:
    def test_empty(self) -> None:
        result = ExtractionResult(tasks=[], incomplete_items=[])
        assert len(result.tasks) == 0
        assert len(result.incomplete_items) == 0


class TestTaskExtractorEmpty:
    def test_empty_text(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        extractor = TaskExtractor(llm)
        result = extractor.extract("")
        assert result.tasks == []
        assert result.incomplete_items == []
        llm.generate.assert_not_called()

    def test_whitespace_text(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        extractor = TaskExtractor(llm)
        result = extractor.extract("   \n  ")
        assert result.tasks == []
        llm.generate.assert_not_called()


class TestTaskExtractorExtraction:
    def test_single_task(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(json.dumps({
            "tasks": [{
                "description": "Call Bob about the project",
                "people": ["Bob"],
                "due_date": "2025-01-15",
                "source_quote": "need to call Bob about the project",
                "urgency": "high",
            }],
            "incomplete_items": [],
        }))

        extractor = TaskExtractor(llm)
        result = extractor.extract("I need to call Bob about the project by next Wednesday")

        assert len(result.tasks) == 1
        task = result.tasks[0]
        assert task.description == "Call Bob about the project"
        assert task.people == ["Bob"]
        assert task.due_date == "2025-01-15"
        assert task.urgency == "high"

    def test_multiple_tasks(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(json.dumps({
            "tasks": [
                {
                    "description": "Send report to Alice",
                    "people": ["Alice"],
                    "due_date": None,
                    "source_quote": "send the report to Alice",
                    "urgency": "medium",
                },
                {
                    "description": "Book restaurant for dinner",
                    "people": [],
                    "due_date": "2025-01-20",
                    "source_quote": "book a restaurant",
                    "urgency": "low",
                },
            ],
            "incomplete_items": [],
        }))

        extractor = TaskExtractor(llm)
        result = extractor.extract("I need to send the report to Alice and book a restaurant")

        assert len(result.tasks) == 2
        assert result.tasks[0].description == "Send report to Alice"
        assert result.tasks[1].description == "Book restaurant for dinner"

    def test_no_tasks_found(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            '{"tasks": [], "incomplete_items": []}'
        )

        extractor = TaskExtractor(llm)
        result = extractor.extract("The weather is nice today")

        assert len(result.tasks) == 0
        assert len(result.incomplete_items) == 0

    def test_with_incomplete_items(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(json.dumps({
            "tasks": [{
                "description": "Order something from Amazon",
                "people": [],
                "due_date": None,
                "source_quote": "order that thing from Amazon",
                "urgency": "low",
            }],
            "incomplete_items": [{
                "description": "Amazon order",
                "missing": "What specific item to order",
            }],
        }))

        extractor = TaskExtractor(llm)
        result = extractor.extract("Don't forget to order that thing from Amazon")

        assert len(result.tasks) == 1
        assert len(result.incomplete_items) == 1
        assert result.incomplete_items[0].missing == "What specific item to order"

    def test_code_block_response(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(
            '```json\n{"tasks": [{"description": "Buy milk", "people": [], '
            '"due_date": null, "source_quote": "buy milk", "urgency": "low"}], '
            '"incomplete_items": []}\n```'
        )

        extractor = TaskExtractor(llm)
        result = extractor.extract("buy milk")

        assert len(result.tasks) == 1
        assert result.tasks[0].description == "Buy milk"

    def test_empty_description_filtered(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(json.dumps({
            "tasks": [
                {"description": "", "people": [], "urgency": "low"},
                {"description": "Valid task", "people": [], "urgency": "medium"},
            ],
            "incomplete_items": [
                {"description": "", "missing": "everything"},
                {"description": "Valid incomplete", "missing": "details"},
            ],
        }))

        extractor = TaskExtractor(llm)
        result = extractor.extract("some conversation")

        assert len(result.tasks) == 1
        assert result.tasks[0].description == "Valid task"
        assert len(result.incomplete_items) == 1
        assert result.incomplete_items[0].description == "Valid incomplete"


class TestTaskExtractorErrors:
    def test_connection_error(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.side_effect = ConnectionError("refused")

        extractor = TaskExtractor(llm)
        result = extractor.extract("some text")

        assert result.tasks == []
        assert result.incomplete_items == []

    def test_runtime_error(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.side_effect = RuntimeError("timeout")

        extractor = TaskExtractor(llm)
        result = extractor.extract("some text")

        assert result.tasks == []

    def test_malformed_json(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response("This is not valid JSON at all")

        extractor = TaskExtractor(llm)
        result = extractor.extract("some text")

        assert result.tasks == []
        assert result.incomplete_items == []

    def test_missing_fields_use_defaults(self) -> None:
        llm = MagicMock(spec=OllamaClient)
        llm.generate.return_value = _make_llm_response(json.dumps({
            "tasks": [{"description": "Minimal task"}],
        }))

        extractor = TaskExtractor(llm)
        result = extractor.extract("do the thing")

        assert len(result.tasks) == 1
        assert result.tasks[0].people == []
        assert result.tasks[0].due_date is None
        assert result.tasks[0].urgency == "medium"
