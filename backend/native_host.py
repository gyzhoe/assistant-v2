"""
Native messaging host for AI Helpdesk Assistant.

Allows the browser extension to start the backend server and Ollama
when they are not already running. Communicates via Chrome/Edge native
messaging protocol (4-byte length prefix + JSON over stdio).

Registered via installer/scripts/register-native-host.ps1.
"""

import json
import os
import struct
import subprocess
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BACKEND_DIR, "native_host.log")


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


def start_backend() -> dict:
    venv_python = os.path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        log(f"venv not found at {venv_python}")
        return {"ok": False, "error": "Backend venv not found. Run setup first."}

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
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        log(f"Started PID={proc.pid}")
        return {"ok": True, "status": "starting", "pid": proc.pid}
    except Exception as e:
        log(f"Error starting backend: {e}")
        return {"ok": False, "error": str(e)}


def start_ollama() -> dict:
    log("Starting Ollama")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return {"ok": True, "status": "starting"}
    except Exception as e:
        log(f"Error starting Ollama: {e}")
        return {"ok": False, "error": str(e)}


def main() -> None:
    msg = read_message()
    if not msg:
        return

    action = msg.get("action", "")
    log(f"Received action: {action}")

    if action == "start_backend":
        send_message(start_backend())
    elif action == "start_ollama":
        send_message(start_ollama())
    else:
        send_message({"ok": False, "error": f"Unknown action: {action}"})


if __name__ == "__main__":
    main()
