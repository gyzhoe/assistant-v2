"""
Native messaging host for AI Helpdesk Assistant.

Allows the browser extension to start and stop the backend server and
llama-server instances via OS-level process management. Communicates via
Chrome/Edge native messaging protocol (4-byte length prefix + JSON over stdio).

Registered via installer/scripts/register-native-host.ps1.
"""

import json
import os
import re
import struct
import subprocess
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BACKEND_DIR)
LLAMA_SERVER_EXE = os.path.join(APP_DIR, "tools", "llama-server.exe")
MODELS_DIR = os.path.join(APP_DIR, "models")
LOG_FILE = os.path.join(BACKEND_DIR, "native_host.log")

# subprocess.CREATE_NO_WINDOW only exists on Windows; use 0 on other platforms
# so tests can run on Linux CI.
_CREATION_FLAGS: int = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def log(msg: str) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def read_message() -> dict | None:
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) < 4:
        return None
    length = struct.unpack("<I", raw_length)[0]
    data = sys.stdin.buffer.read(length)
    return json.loads(data.decode("utf-8"))


def send_message(msg: dict) -> None:
    encoded = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _find_pids_on_port(port: int) -> list[int]:
    """Parse ``netstat -ano -p TCP`` to find PIDs listening on *port*."""
    try:
        output = subprocess.check_output(
            ["netstat", "-ano", "-p", "TCP"],
            text=True,
            creationflags=_CREATION_FLAGS,
        )
    except Exception:
        return []

    pids: set[int] = set()
    pattern = re.compile(rf":\s*{port}\s+.*LISTENING\s+(\d+)", re.IGNORECASE)
    for line in output.splitlines():
        m = pattern.search(line)
        if m:
            pid = int(m.group(1))
            if pid != 0:
                pids.add(pid)
    return sorted(pids)


def _is_port_listening(port: int) -> bool:
    """Check if any process is listening on the given port."""
    return len(_find_pids_on_port(port)) > 0


def _kill_legacy_ollama() -> None:
    """Kill leftover Ollama processes to avoid port conflicts on upgrade."""
    for exe in ("ollama.exe", "ollama_llama_server.exe"):
        try:
            subprocess.run(
                ["taskkill", "/IM", exe, "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATION_FLAGS,
            )
        except Exception as e:
            log(f"_kill_legacy_ollama: failed to kill {exe}: {e}")


def start_backend() -> dict:
    venv_python = os.path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        log(f"venv not found at {venv_python}")
        return {"ok": False, "error": "Backend venv not found. Run setup first."}

    # Kill leftover Ollama processes to avoid port conflicts on upgrade
    _kill_legacy_ollama()

    # Start llama-server instances if not already running
    llm_started = False
    if not _is_port_listening(11435):
        llm_started = _start_llama_servers()

    log_out = os.path.join(BACKEND_DIR, "backend_stdout.log")
    log_err = os.path.join(BACKEND_DIR, "backend_stderr.log")
    log(f"Starting backend with {venv_python}, cwd={BACKEND_DIR}")

    try:
        with open(log_out, "w") as fout, open(log_err, "w") as ferr:
            proc = subprocess.Popen(
                [venv_python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"],
                cwd=BACKEND_DIR,
                stdout=fout,
                stderr=ferr,
                creationflags=_CREATION_FLAGS,
            )
        log(f"Started PID={proc.pid}")
        return {"ok": True, "status": "starting", "pid": proc.pid, "llm_started": llm_started}
    except Exception as e:
        log(f"Error starting backend: {e}")
        return {"ok": False, "error": str(e)}


def _start_llama_servers() -> bool:
    """Start both LLM and embed llama-server instances."""
    llama_exe = LLAMA_SERVER_EXE if os.path.exists(LLAMA_SERVER_EXE) else "llama-server"
    log(f"Starting llama-server instances: {llama_exe}")

    try:
        # LLM server
        llm_model = os.path.join(MODELS_DIR, "qwen3.5-9b-q4_k_m.gguf")
        subprocess.Popen(
            [
                llama_exe, "-m", llm_model,
                "--port", "11435",
                "--n-gpu-layers", "-1",
                "--ctx-size", "8192",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATION_FLAGS,
        )

        # Embed server
        embed_model = os.path.join(MODELS_DIR, "nomic-embed-text-v1.5.Q8_0.gguf")
        subprocess.Popen(
            [
                llama_exe, "-m", embed_model,
                "--port", "11436",
                "--embedding",
                "--n-gpu-layers", "-1",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATION_FLAGS,
        )
        return True
    except Exception as e:
        log(f"Warning: could not start llama-server: {e}")
        return False


def get_token() -> dict:
    """Read API_TOKEN from backend/.env for extension auto-configuration."""
    env_path = os.path.join(BACKEND_DIR, ".env")
    if not os.path.exists(env_path):
        log(f".env not found at {env_path}")
        return {"ok": False, "error": ".env file not found"}

    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("API_TOKEN="):
                    value = line[len("API_TOKEN="):]
                    # Strip surrounding quotes
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    value = value.strip()
                    if not value or value == "REPLACE_WITH_STRONG_SECRET":
                        log("API_TOKEN is placeholder or empty")
                        return {"ok": False, "error": "API_TOKEN not configured"}
                    return {"ok": True, "token": value}
        return {"ok": False, "error": "API_TOKEN not found in .env"}
    except Exception as e:
        log(f"Error reading .env: {e}")
        return {"ok": False, "error": str(e)}


def start_llm() -> dict:
    """Start llama-server instances."""
    # Kill leftover Ollama processes to avoid port conflicts on upgrade
    _kill_legacy_ollama()

    ok = _start_llama_servers()
    if ok:
        return {"ok": True, "status": "starting"}
    return {"ok": False, "error": "Failed to start llama-server"}


def _kill_llm() -> None:
    """Kill llama-server processes (shared by stop_backend and stop_llm)."""
    try:
        subprocess.run(
            ["taskkill", "/IM", "llama-server.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATION_FLAGS,
        )
    except Exception as e:
        log(f"_kill_llm: failed to kill llama-server.exe: {e}")


def stop_backend() -> dict:
    """Stop the backend and llama-server (symmetric with start_backend which starts both)."""
    pids = _find_pids_on_port(8765)
    if not pids:
        log("stop_backend: no process found on port 8765")
    else:
        log(f"stop_backend: killing PIDs {pids}")
        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_CREATION_FLAGS,
                )
            except Exception as e:
                log(f"stop_backend: failed to kill PID {pid}: {e}")

    log("stop_backend: also killing llama-server (symmetric with start_backend)")
    _kill_llm()

    return {"ok": True, "status": "stopped", "pids": pids if pids else [], "llm_stopped": True}


def stop_llm() -> dict:
    """Stop llama-server processes."""
    log("stop_llm: killing llama-server.exe")
    _kill_llm()
    return {"ok": True, "status": "stopped"}


def main() -> None:
    msg = read_message()
    if not msg:
        return

    action = msg.get("action", "")
    log(f"Received action: {action}")

    if action == "start_backend":
        send_message(start_backend())
    elif action == "start_llm":
        send_message(start_llm())
    elif action == "stop_backend":
        send_message(stop_backend())
    elif action == "stop_llm":
        send_message(stop_llm())
    elif action == "get_token":
        send_message(get_token())
    else:
        send_message({"ok": False, "error": f"Unknown action: {action}"})


if __name__ == "__main__":
    main()
