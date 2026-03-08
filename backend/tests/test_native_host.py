"""Tests for native_host.py — get_token, stop_backend, stop_llm, start_backend,
start_llm actions and port-targeted kill logic."""

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
    def test_kills_by_port_not_image_name(self):
        """_kill_llm uses port-targeted kill, not taskkill /IM."""
        with (
            patch("native_host._find_pids_on_port") as mock_find,
            patch("native_host._kill_pids") as mock_kill,
        ):
            mock_find.side_effect = lambda port: {11435: [100], 11436: [200]}[port]
            native_host._kill_llm()

        # Called for both ports
        assert mock_find.call_count == 2
        mock_kill.assert_called_once_with([100, 200])

    def test_no_pids_found(self):
        """_kill_llm handles case where no PIDs are on the ports."""
        with (
            patch("native_host._find_pids_on_port", return_value=[]),
            patch("native_host._kill_pids") as mock_kill,
        ):
            native_host._kill_llm()

        mock_kill.assert_not_called()


class TestKillPids:
    def test_kills_each_pid(self):
        with patch("native_host.subprocess.run") as mock_run:
            native_host._kill_pids([100, 200])

        assert mock_run.call_count == 2
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert ["taskkill", "/PID", "100", "/T", "/F"] in calls
        assert ["taskkill", "/PID", "200", "/T", "/F"] in calls


class TestStopBackend:
    def test_kills_found_pids_and_llm(self):
        with (
            patch("native_host._find_pids_on_port") as mock_find,
            patch("native_host.subprocess.run") as mock_run,
            patch("native_host._kill_pids") as mock_kill_pids,
        ):
            # First call for port 8765, then for 11435, then for 11436
            mock_find.side_effect = lambda port: {
                8765: [5432], 11435: [100], 11436: [200],
            }.get(port, [])
            result = native_host.stop_backend()

        assert result["ok"] is True
        assert result["status"] == "stopped"
        assert result["pids"] == [5432]
        assert result["llm_stopped"] is True
        # Backend PID killed via subprocess.run
        assert mock_run.call_count == 1
        # LLM PIDs killed via _kill_pids
        mock_kill_pids.assert_called_once_with([100, 200])

    def test_still_kills_llm_when_no_backend_pids(self):
        with (
            patch("native_host._find_pids_on_port") as mock_find,
            patch("native_host.subprocess.run"),
            patch("native_host._kill_pids") as mock_kill_pids,
        ):
            mock_find.side_effect = lambda port: {
                8765: [], 11435: [100], 11436: [],
            }.get(port, [])
            result = native_host.stop_backend()

        assert result["ok"] is True
        assert result["status"] == "stopped"
        assert result["pids"] == []
        assert result["llm_stopped"] is True
        mock_kill_pids.assert_called_once_with([100])


class TestStopLlm:
    def test_kills_llama_server_by_port(self):
        with (
            patch("native_host._find_pids_on_port") as mock_find,
            patch("native_host._kill_pids") as mock_kill,
        ):
            mock_find.side_effect = lambda port: {11435: [100], 11436: [200]}[port]
            result = native_host.stop_llm()

        assert result == {"ok": True, "status": "stopped"}
        mock_kill.assert_called_once_with([100, 200])


class TestStartBackend:
    def test_returns_error_when_port_8765_in_use(self, env_dir):
        """start_backend rejects if port 8765 is already occupied."""
        venv_python = env_dir / ".venv" / "Scripts" / "python.exe"
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()

        with (
            patch("native_host.BACKEND_DIR", str(env_dir)),
            patch("native_host._is_port_listening") as mock_port,
        ):
            mock_port.return_value = True
            result = native_host.start_backend()

        assert result["ok"] is False
        assert "already running" in result["error"]

    def test_starts_when_port_free(self, env_dir):
        """start_backend proceeds when port 8765 is free."""
        venv_python = env_dir / ".venv" / "Scripts" / "python.exe"
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()

        with (
            patch("native_host.BACKEND_DIR", str(env_dir)),
            patch("native_host._is_port_listening", return_value=False),
            patch("native_host._kill_legacy_ollama"),
            patch("native_host._start_llama_servers", return_value=False),
            patch("native_host.subprocess.Popen") as mock_popen,
        ):
            mock_popen.return_value.pid = 9999
            result = native_host.start_backend()

        assert result["ok"] is True
        assert result["status"] == "starting"


class TestStartLlm:
    def test_returns_already_running_when_both_servers_up(self):
        """start_llm returns already_running when both ports are listening."""
        with (
            patch("native_host._kill_legacy_ollama"),
            patch("native_host._is_port_listening") as mock_port,
        ):
            mock_port.side_effect = lambda port: port in (11435, 11436)
            result = native_host.start_llm()

        assert result["ok"] is True
        assert result["status"] == "already_running"

    def test_starts_only_missing_servers(self):
        """start_llm passes skip flags when one server is already running."""
        with (
            patch("native_host._kill_legacy_ollama"),
            patch("native_host._is_port_listening") as mock_port,
            patch("native_host._start_llama_servers", return_value=True) as mock_start,
        ):
            # LLM running, embed not
            mock_port.side_effect = lambda port: port == 11435
            result = native_host.start_llm()

        assert result["ok"] is True
        assert result["status"] == "starting"
        mock_start.assert_called_once_with(skip_llm=True, skip_embed=False)


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
