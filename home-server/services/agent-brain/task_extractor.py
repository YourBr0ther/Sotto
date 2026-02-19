"""Task extraction from transcribed text."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from llm_client import OllamaClient

logger = logging.getLogger(__name__)

TASK_EXTRACTION_PROMPT = """You are a task extraction system for an ambient AI assistant.
Your job is to identify actionable tasks from transcribed conversations.

For each task found, extract:
- description: What needs to be done
- people: Names of people involved (list)
- due_date: Any mentioned deadline (ISO format or null)
- source_quote: The relevant part of the conversation
- urgency: low, medium, or high

Also extract any incomplete information that needs follow-up:
- incomplete_items: Things mentioned but missing details

Respond with ONLY a JSON object:
{
  "tasks": [
    {
      "description": "...",
      "people": ["..."],
      "due_date": null or "YYYY-MM-DD",
      "source_quote": "...",
      "urgency": "low|medium|high"
    }
  ],
  "incomplete_items": [
    {
      "description": "...",
      "missing": "what information is missing"
    }
  ]
}

If no tasks are found, return {"tasks": [], "incomplete_items": []}"""


@dataclass
class ExtractedTask:
    """A task extracted from conversation."""

    description: str
    people: list[str] = field(default_factory=list)
    due_date: str | None = None
    source_quote: str = ""
    urgency: str = "medium"


@dataclass
class IncompleteItem:
    """An incomplete information item needing follow-up."""

    description: str
    missing: str


@dataclass
class ExtractionResult:
    """Result of task extraction."""

    tasks: list[ExtractedTask]
    incomplete_items: list[IncompleteItem]


class TaskExtractor:
    """Extracts tasks and action items from transcribed text."""

    def __init__(self, llm_client: OllamaClient) -> None:
        self._llm = llm_client

    def extract(self, text: str) -> ExtractionResult:
        """Extract tasks from transcribed text.

        Args:
            text: Transcribed conversation text.

        Returns:
            ExtractionResult with tasks and incomplete items.
        """
        if not text.strip():
            return ExtractionResult(tasks=[], incomplete_items=[])

        try:
            response = self._llm.generate(
                prompt=f"Extract tasks from this conversation:\n\n{text}",
                system=TASK_EXTRACTION_PROMPT,
                temperature=0.1,
            )
            return self._parse_response(response.text)

        except (ConnectionError, RuntimeError) as e:
            logger.error("Task extraction failed: %s", e)
            return ExtractionResult(tasks=[], incomplete_items=[])

    def _parse_response(self, response_text: str) -> ExtractionResult:
        """Parse the LLM's extraction response."""
        try:
            text = response_text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)

            tasks = [
                ExtractedTask(
                    description=t.get("description", ""),
                    people=t.get("people", []),
                    due_date=t.get("due_date"),
                    source_quote=t.get("source_quote", ""),
                    urgency=t.get("urgency", "medium"),
                )
                for t in data.get("tasks", [])
                if t.get("description")
            ]

            incomplete = [
                IncompleteItem(
                    description=i.get("description", ""),
                    missing=i.get("missing", ""),
                )
                for i in data.get("incomplete_items", [])
                if i.get("description")
            ]

            return ExtractionResult(tasks=tasks, incomplete_items=incomplete)

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse extraction response: %s", e)
            return ExtractionResult(tasks=[], incomplete_items=[])
