"""Tests for the Ollama LLM client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_client import LLMResponse, OllamaClient


class TestLLMResponse:
    def test_dataclass_fields(self) -> None:
        resp = LLMResponse(text="hello", model="llama3.1:8b", tokens_used=10, done=True)
        assert resp.text == "hello"
        assert resp.model == "llama3.1:8b"
        assert resp.tokens_used == 10
        assert resp.done is True


class TestOllamaClientInit:
    def test_defaults(self) -> None:
        client = OllamaClient()
        assert client.model == "llama3.1:8b"
        assert client._base_url == "http://localhost:11434"
        assert client._timeout == 120

    def test_custom_params(self) -> None:
        client = OllamaClient(
            base_url="http://myhost:1234/",
            model="mistral:7b",
            timeout=60,
        )
        assert client._base_url == "http://myhost:1234"
        assert client.model == "mistral:7b"
        assert client._timeout == 60

    def test_trailing_slash_stripped(self) -> None:
        client = OllamaClient(base_url="http://host:1234///")
        assert client._base_url == "http://host:1234"


class TestOllamaClientHealthCheck:
    @patch("llm_client.requests.get")
    def test_healthy(self, mock_get: MagicMock) -> None:
        mock_get.return_value.status_code = 200
        client = OllamaClient()
        assert client.check_health() is True
        mock_get.assert_called_once_with("http://localhost:11434/api/tags", timeout=5)

    @patch("llm_client.requests.get")
    def test_unhealthy_status(self, mock_get: MagicMock) -> None:
        mock_get.return_value.status_code = 500
        client = OllamaClient()
        assert client.check_health() is False

    @patch("llm_client.requests.get")
    def test_connection_error(self, mock_get: MagicMock) -> None:
        import requests
        mock_get.side_effect = requests.ConnectionError("refused")
        client = OllamaClient()
        assert client.check_health() is False


class TestOllamaClientGenerate:
    @patch("llm_client.requests.post")
    def test_generate_success(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "response": "The answer is 42.",
            "model": "llama3.1:8b",
            "eval_count": 15,
            "done": True,
        }
        mock_post.return_value.raise_for_status = MagicMock()

        client = OllamaClient()
        result = client.generate("What is the answer?", system="Be helpful")

        assert result.text == "The answer is 42."
        assert result.model == "llama3.1:8b"
        assert result.tokens_used == 15
        assert result.done is True

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["prompt"] == "What is the answer?"
        assert payload["system"] == "Be helpful"
        assert payload["options"]["temperature"] == 0.7
        assert payload["stream"] is False

    @patch("llm_client.requests.post")
    def test_generate_no_system(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "response": "ok",
            "done": True,
        }
        mock_post.return_value.raise_for_status = MagicMock()

        client = OllamaClient()
        client.generate("hello")

        payload = mock_post.call_args[1]["json"]
        assert "system" not in payload

    @patch("llm_client.requests.post")
    def test_generate_custom_temperature(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"response": "ok", "done": True}
        mock_post.return_value.raise_for_status = MagicMock()

        client = OllamaClient()
        client.generate("hello", temperature=0.1)

        payload = mock_post.call_args[1]["json"]
        assert payload["options"]["temperature"] == 0.1

    @patch("llm_client.requests.post")
    def test_generate_connection_error(self, mock_post: MagicMock) -> None:
        import requests
        mock_post.side_effect = requests.ConnectionError("refused")

        client = OllamaClient()
        with pytest.raises(ConnectionError, match="Cannot reach Ollama"):
            client.generate("hello")

    @patch("llm_client.requests.post")
    def test_generate_http_error(self, mock_post: MagicMock) -> None:
        import requests
        mock_post.return_value.raise_for_status.side_effect = requests.HTTPError("500")

        client = OllamaClient()
        with pytest.raises(RuntimeError, match="Ollama generation failed"):
            client.generate("hello")

    @patch("llm_client.requests.post")
    def test_generate_timeout(self, mock_post: MagicMock) -> None:
        import requests
        mock_post.side_effect = requests.Timeout()

        client = OllamaClient()
        with pytest.raises(RuntimeError, match="timed out"):
            client.generate("hello")


class TestOllamaClientChat:
    @patch("llm_client.requests.post")
    def test_chat_success(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "I'm doing well."},
            "model": "llama3.1:8b",
            "eval_count": 8,
            "done": True,
        }
        mock_post.return_value.raise_for_status = MagicMock()

        client = OllamaClient()
        messages = [
            {"role": "user", "content": "How are you?"},
        ]
        result = client.chat(messages)

        assert result.text == "I'm doing well."
        assert result.tokens_used == 8

        payload = mock_post.call_args[1]["json"]
        assert payload["messages"] == messages
        assert payload["stream"] is False

    @patch("llm_client.requests.post")
    def test_chat_connection_error(self, mock_post: MagicMock) -> None:
        import requests
        mock_post.side_effect = requests.ConnectionError("refused")

        client = OllamaClient()
        with pytest.raises(ConnectionError, match="Cannot reach Ollama"):
            client.chat([{"role": "user", "content": "hi"}])

    @patch("llm_client.requests.post")
    def test_chat_http_error(self, mock_post: MagicMock) -> None:
        import requests
        mock_post.return_value.raise_for_status.side_effect = requests.HTTPError("bad")

        client = OllamaClient()
        with pytest.raises(RuntimeError, match="Ollama chat failed"):
            client.chat([{"role": "user", "content": "hi"}])
