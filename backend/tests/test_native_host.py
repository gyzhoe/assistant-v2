"""Tests for native_host.py get_token action."""

import os
import sys
from unittest.mock import patch

import pytest

# native_host.py lives in backend/ (not a package under app/), so add it to sys.path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import native_host  # noqa: E402


@pytest.fixture()
def env_dir(tmp_path):
    """Provide a temporary directory that stands in for BACKEND_DIR."""
    return tmp_path


def _write_env(env_dir, content: str) -> None:
    (env_dir / ".env").write_text(content, encoding="utf-8")


def _get_token(env_dir):
    """Call get_token with patched BACKEND_DIR."""
    with patch("native_host.BACKEND_DIR", str(env_dir)):
        return native_host.get_token()


class TestGetToken:
    def test_reads_valid_token(self, env_dir):
        _write_env(env_dir, "OLLAMA_BASE_URL=http://localhost:11434\nAPI_TOKEN=abc123def456\n")
        result = _get_token(env_dir)
        assert result == {"ok": True, "token": "abc123def456"}

    def test_missing_env_file(self, env_dir):
        result = _get_token(env_dir)
        assert result["ok"] is False
        assert ".env file not found" in result["error"]

    def test_skips_placeholder(self, env_dir):
        _write_env(env_dir, "API_TOKEN=REPLACE_WITH_STRONG_SECRET\n")
        result = _get_token(env_dir)
        assert result["ok"] is False
        assert "not configured" in result["error"]

    def test_skips_empty_value(self, env_dir):
        _write_env(env_dir, "API_TOKEN=\n")
        result = _get_token(env_dir)
        assert result["ok"] is False

    def test_strips_double_quotes(self, env_dir):
        _write_env(env_dir, 'API_TOKEN="my_secret_token"\n')
        result = _get_token(env_dir)
        assert result == {"ok": True, "token": "my_secret_token"}

    def test_strips_single_quotes(self, env_dir):
        _write_env(env_dir, "API_TOKEN='my_secret_token'\n")
        result = _get_token(env_dir)
        assert result == {"ok": True, "token": "my_secret_token"}

    def test_no_api_token_line(self, env_dir):
        _write_env(env_dir, "OLLAMA_BASE_URL=http://localhost:11434\n")
        result = _get_token(env_dir)
        assert result["ok"] is False
        assert "not found" in result["error"]
