"""Tests for the structured audit logger (app.services.audit)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.audit import _AUDIT_LOG_FILE, audit_log, reset_audit_logger


@pytest.fixture(autouse=True)
def _clean_audit_logger(tmp_path: Path) -> None:  # type: ignore[misc]
    """Reset the audit logger singleton before each test and redirect to tmp."""
    reset_audit_logger()
    with patch("app.services.audit._AUDIT_LOG_FILE", tmp_path / "audit.log"):
        yield
    reset_audit_logger()


def _read_log(tmp_path: Path) -> list[dict[str, str]]:
    """Read all JSON entries from the temp audit log."""
    log_file = tmp_path / "audit.log"
    if not log_file.exists():
        return []
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


def test_audit_log_writes_json_entry(tmp_path: Path) -> None:
    """audit_log should write a valid JSON entry to the log file."""
    audit_log("login", client_ip="127.0.0.1", outcome="success")

    entries = _read_log(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["action"] == "login"
    assert entry["client_ip"] == "127.0.0.1"
    assert entry["outcome"] == "success"
    assert "timestamp" in entry


def test_audit_log_includes_session_prefix(tmp_path: Path) -> None:
    """When session_id is provided, only first 8 chars should appear."""
    audit_log(
        "login",
        client_ip="10.0.0.1",
        session_id="abcdefghijklmnop1234567890",
    )

    entries = _read_log(tmp_path)
    assert len(entries) == 1
    assert entries[0]["session_prefix"] == "abcdefgh"
    assert "session_id" not in entries[0]


def test_audit_log_includes_detail(tmp_path: Path) -> None:
    """The detail field should appear when provided."""
    audit_log(
        "article_delete",
        client_ip="127.0.0.1",
        detail="article_id=abc123 chunks=5",
    )

    entries = _read_log(tmp_path)
    assert entries[0]["detail"] == "article_id=abc123 chunks=5"


def test_audit_log_omits_empty_optional_fields(tmp_path: Path) -> None:
    """session_prefix and detail should not appear when empty."""
    audit_log("shutdown", client_ip="::1")

    entries = _read_log(tmp_path)
    assert "session_prefix" not in entries[0]
    assert "detail" not in entries[0]


def test_audit_log_failure_outcome(tmp_path: Path) -> None:
    """Failure outcome should be recorded correctly."""
    audit_log("login", client_ip="192.168.1.5", outcome="failure")

    entries = _read_log(tmp_path)
    assert entries[0]["outcome"] == "failure"


def test_audit_log_multiple_entries(tmp_path: Path) -> None:
    """Multiple audit_log calls should append entries."""
    audit_log("login", client_ip="10.0.0.1")
    audit_log("article_delete", client_ip="10.0.0.1", detail="id=x")
    audit_log("logout", client_ip="10.0.0.1")

    entries = _read_log(tmp_path)
    assert len(entries) == 3
    assert [e["action"] for e in entries] == [
        "login", "article_delete", "logout",
    ]


def test_audit_log_default_file_path() -> None:
    """The default log file should be 'audit.log'."""
    assert _AUDIT_LOG_FILE == Path("audit.log")
