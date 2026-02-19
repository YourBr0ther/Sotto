"""LLM client for Sotto agent brain - interfaces with Ollama."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from the LLM."""

    text: str
    model: str
    tokens_used: int
    done: bool


class OllamaClient:
    """Client for the Ollama local LLM API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        timeout: int = 120,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def check_health(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            resp = requests.get(f"{self._base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def generate(self, prompt: str, system: str = "", temperature: float = 0.7) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: The user/context prompt.
            system: Optional system prompt.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with the generated text.

        Raises:
            ConnectionError: If Ollama is unreachable.
            RuntimeError: If generation fails.
        """
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            return LLMResponse(
                text=data.get("response", ""),
                model=data.get("model", self._model),
                tokens_used=data.get("eval_count", 0),
                done=data.get("done", True),
            )
        except requests.ConnectionError as e:
            raise ConnectionError(f"Cannot reach Ollama at {self._base_url}: {e}") from e
        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama generation failed: {e}") from e
        except requests.Timeout:
            raise RuntimeError("Ollama generation timed out")

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> LLMResponse:
        """Chat with the LLM using a message history.

        Args:
            messages: List of {"role": "system|user|assistant", "content": "..."} dicts.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with the assistant's reply.
        """
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            message = data.get("message", {})
            return LLMResponse(
                text=message.get("content", ""),
                model=data.get("model", self._model),
                tokens_used=data.get("eval_count", 0),
                done=data.get("done", True),
            )
        except requests.ConnectionError as e:
            raise ConnectionError(f"Cannot reach Ollama: {e}") from e
        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama chat failed: {e}") from e
