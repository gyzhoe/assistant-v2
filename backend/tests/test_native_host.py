"""Tests for native_host.py — get_token, stop_backend, stop_llm actions."""

import json
import os
import struct
import sys
from io import BytesIO
from unittest.mock import MagicMock, patch

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
        _write_env(env_dir, "LLM_BASE_URL=http://localhost:11435\nAPI_TOKEN=abc123def456\n")
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
        _write_env(env_dir, "LLM_BASE_URL=http://localhost:11435\n")
        result = _get_token(env_dir)
        assert result["ok"] is False
        assert "not found" in result["error"]


# --- netstat output samples for _find_pids_on_port tests ---

NETSTAT_SAMPLE = """\
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1104
  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       5432
  TCP    127.0.0.1:8765         127.0.0.1:54321        ESTABLISHED     5432
  TCP    0.0.0.0:49664          0.0.0.0:0              LISTENING       788
"""

NETSTAT_MULTI_PID = """\
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       5432
  TCP    0.0.0.0:8765           0.0.0.0:0              LISTENING       9999
"""


class TestFindPidsOnPort:
    def test_finds_listening_pid(self):
        with patch("native_host.subprocess.check_output", return_value=NETSTAT_SAMPLE):
            pids = native_host._find_pids_on_port(8765)
        assert pids == [5432]

    def test_finds_multiple_pids(self):
        with patch("native_host.subprocess.check_output", return_value=NETSTAT_MULTI_PID):
            pids = native_host._find_pids_on_port(8765)
        assert pids == [5432, 9999]

    def test_empty_output(self):
        with patch("native_host.subprocess.check_output", return_value=""):
            pids = native_host._find_pids_on_port(8765)
        assert pids == []

    def test_no_match_on_different_port(self):
        with patch("native_host.subprocess.check_output", return_value=NETSTAT_SAMPLE):
            pids = native_host._find_pids_on_port(9999)
        assert pids == []

    def test_returns_empty_on_subprocess_error(self):
        with patch("native_host.subprocess.check_output", side_effect=OSError("fail")):
            pids = native_host._find_pids_on_port(8765)
        assert pids == []


class TestKillLlm:
    def test_kills_llama_server(self):
        with patch("native_host.subprocess.run") as mock_run:
            native_host._kill_llm()
        assert mock_run.call_count == 1
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert ["taskkill", "/IM", "llama-server.exe", "/F"] in calls


class TestStopBackend:
    def test_kills_found_pids_and_llm(self):
        with (
            patch("native_host._find_pids_on_port", return_value=[5432]),
            patch("native_host.subprocess.run") as mock_run,
        ):
            result = native_host.stop_backend()
        assert result["ok"] is True
        assert result["status"] == "stopped"
        assert result["pids"] == [5432]
        assert result["llm_stopped"] is True
        # 1 taskkill for backend PID + 1 for llama-server
        assert mock_run.call_count == 2

    def test_still_kills_llm_when_no_backend_pids(self):
        with (
            patch("native_host._find_pids_on_port", return_value=[]),
            patch("native_host.subprocess.run") as mock_run,
        ):
            result = native_host.stop_backend()
        assert result["ok"] is True
        assert result["status"] == "stopped"
        assert result["pids"] == []
        assert result["llm_stopped"] is True
        # 1 taskkill call for llama-server only
        assert mock_run.call_count == 1

    def test_kills_multiple_pids_and_llm(self):
        with (
            patch("native_host._find_pids_on_port", return_value=[100, 200]),
            patch("native_host.subprocess.run") as mock_run,
        ):
            result = native_host.stop_backend()
        assert result["ok"] is True
        assert result["pids"] == [100, 200]
        assert result["llm_stopped"] is True
        # 2 backend PIDs + 1 llama-server
        assert mock_run.call_count == 3


class TestStopLlm:
    def test_kills_llama_server(self):
        with patch("native_host.subprocess.run") as mock_run:
            result = native_host.stop_llm()
        assert result == {"ok": True, "status": "stopped"}
        assert mock_run.call_count == 1
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert ["taskkill", "/IM", "llama-server.exe", "/F"] in calls


def _make_native_message(payload: dict) -> bytes:
    """Encode a dict as a native-messaging stdin frame (4-byte LE length + JSON)."""
    encoded = json.dumps(payload).encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded


class TestMainDispatch:
    def test_dispatch_stop_backend(self):
        stdin_bytes = _make_native_message({"action": "stop_backend"})
        stdout_buf = BytesIO()
        with (
            patch("native_host.sys.stdin", MagicMock(buffer=BytesIO(stdin_bytes))),
            patch("native_host.sys.stdout", MagicMock(buffer=stdout_buf)),
            patch("native_host.stop_backend", return_value={"ok": True, "status": "stopped", "pids": [1]}),
        ):
            native_host.main()
        stdout_buf.seek(0)
        length = struct.unpack("<I", stdout_buf.read(4))[0]
        response = json.loads(stdout_buf.read(length).decode("utf-8"))
        assert response["ok"] is True
        assert response["status"] == "stopped"

    def test_dispatch_stop_llm(self):
        stdin_bytes = _make_native_message({"action": "stop_llm"})
        stdout_buf = BytesIO()
        with (
            patch("native_host.sys.stdin", MagicMock(buffer=BytesIO(stdin_bytes))),
            patch("native_host.sys.stdout", MagicMock(buffer=stdout_buf)),
            patch("native_host.stop_llm", return_value={"ok": True, "status": "stopped"}),
        ):
            native_host.main()
        stdout_buf.seek(0)
        length = struct.unpack("<I", stdout_buf.read(4))[0]
        response = json.loads(stdout_buf.read(length).decode("utf-8"))
        assert response["ok"] is True
        assert response["status"] == "stopped"
