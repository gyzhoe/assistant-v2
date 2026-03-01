"""Tests for the structured JSON logging configuration."""

from __future__ import annotations

import json
import logging

from app.logging_config import JSONFormatter, setup_logging


def test_json_formatter_basic() -> None:
    """JSONFormatter should produce valid JSON with required fields."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Hello %s",
        args=("world",),
        exc_info=None,
    )
    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "Hello world"
    assert "timestamp" in data
    assert "exception" not in data


def test_json_formatter_exception_path() -> None:
    """JSONFormatter should include exception info when present."""
    formatter = JSONFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Something failed",
            args=(),
            exc_info=True,
        )
        # LogRecord with exc_info=True captures sys.exc_info() automatically
        import sys

        record.exc_info = sys.exc_info()

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "ERROR"
    assert "exception" in data
    assert "ValueError" in data["exception"]
    assert "test error" in data["exception"]


def test_setup_logging_configures_root() -> None:
    """setup_logging should set up the root logger with JSONFormatter handler."""
    setup_logging(level="DEBUG")

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) >= 1

    # At least one handler should use JSONFormatter
    json_handlers = [h for h in root.handlers if isinstance(h.formatter, JSONFormatter)]
    assert len(json_handlers) >= 1

    # Restore to avoid affecting other tests
    setup_logging(level="INFO")
