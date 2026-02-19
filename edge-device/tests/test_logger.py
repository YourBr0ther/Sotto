"""Tests for the structured logger."""

import json
import logging

import pytest

from utils.logger import JsonFormatter, setup_logging


class TestJsonFormatter:
    def test_formats_as_json(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        result = formatter.format(record)
        data = json.loads(result)
        assert data["message"] == "Hello world"
        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert "timestamp" in data

    def test_formats_exceptions(self) -> None:
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=exc_info,
            )
            result = formatter.format(record)
            data = json.loads(result)
            assert "exception" in data
            assert "ValueError" in data["exception"]


class TestSetupLogging:
    def test_setup_json_logging(self) -> None:
        setup_logging(level="DEBUG", json_output=True)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)

    def test_setup_plain_logging(self) -> None:
        setup_logging(level="INFO", json_output=False)
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert not isinstance(root.handlers[0].formatter, JsonFormatter)

    def test_clears_previous_handlers(self) -> None:
        root = logging.getLogger()
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())
        setup_logging()
        assert len(root.handlers) == 1
