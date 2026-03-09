"""
Native messaging host for AI Helpdesk Assistant.

Allows the browser extension to start and stop the backend server and
llama-server instances via OS-level process management. Communicates via
Chrome/Edge native messaging protocol (4-byte length prefix + JSON over stdio).

Registered via installer/scripts/register-native-host.ps1.
"""

import json
import os
import struct
import subprocess
import sys

from app.process_utils import (
    APP_DIR,
    BACKEND_DIR,
    BACKEND_PORT,
    BUNDLED_LLAMA_SERVER,
    CREATION_FLAGS,
    EMBED_GGUF_FILE,
    EMBED_PORT,
    LLM_PORT,
    MODELS_DIR,
    detect_gpu_config,
    find_pids_on_port,
    is_port_listening,
    kill_legacy_ollama,
    kill_llama_server,
    kill_pids,
)

LOG_FILE = os.path.join(str(BACKEND_DIR), "native_host.log")


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
    backend_dir = str(BACKEND_DIR)
    venv_python = os.path.join(backend_dir, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        log(f"venv not found at {venv_python}")
        return {"ok": False, "error": "Backend venv not found. Run setup first."}

    # Check if backend is already running on port 8765
    if is_port_listening(BACKEND_PORT):
        log("start_backend: port 8765 already in use, backend likely running")
        return {"ok": False, "error": "Backend already running on port 8765."}

    # Kill leftover Ollama processes to avoid port conflicts on upgrade
    kill_legacy_ollama()

    # Start llama-server instances if not already running
    llm_started = False
    if not is_port_listening(LLM_PORT):
        llm_started = _start_llama_servers()

    log_out = os.path.join(backend_dir, "backend_stdout.log")
    log_err = os.path.join(backend_dir, "backend_stderr.log")
    log(f"Starting backend with {venv_python}, cwd={backend_dir}")

    try:
        with open(log_out, "w") as fout, open(log_err, "w") as ferr:
            proc = subprocess.Popen(
                [venv_python, "-m", "uvicorn", "app.main:app",
                 "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
                cwd=backend_dir,
                stdout=fout,
                stderr=ferr,
                creationflags=CREATION_FLAGS,
            )
        log(f"Started PID={proc.pid}")
        return {
            "ok": True, "status": "starting",
            "pid": proc.pid, "llm_started": llm_started,
        }
    except Exception as e:
        log(f"Error starting backend: {e}")
        return {"ok": False, "error": str(e)}


def _start_llama_servers(
    *, skip_llm: bool = False, skip_embed: bool = False,
) -> bool:
    """Start LLM and/or embed llama-server instances.

    Args:
        skip_llm: If True, skip starting the LLM server (already running).
        skip_embed: If True, skip starting the embed server (already running).
    """
    llama_exe = str(BUNDLED_LLAMA_SERVER) if BUNDLED_LLAMA_SERVER.exists() else "llama-server"
    log(f"Starting llama-server instances: {llama_exe} (skip_llm={skip_llm}, skip_embed={skip_embed})")

    n_gpu_layers, ctx_size = detect_gpu_config(log_fn=log)
    logs_dir = APP_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)

    llm_log = None
    embed_log = None
    try:
        if not skip_llm:
            # LLM server — use default model GGUF
            from app.config import settings
            from app.constants import MODEL_GGUF_FILES
            gguf_name = MODEL_GGUF_FILES.get(settings.default_model, "Qwen3.5-9B-Q4_K_M.gguf")
            llm_model = str(MODELS_DIR / gguf_name)
            llm_log = open(str(logs_dir / "llm_server.log"), "w")  # noqa: SIM115
            subprocess.Popen(
                [
                    llama_exe, "-m", llm_model,
                    "--port", str(LLM_PORT),
                    "--n-gpu-layers", n_gpu_layers,
                    "--ctx-size", ctx_size,
                ],
                stdout=llm_log,
                stderr=llm_log,
                creationflags=CREATION_FLAGS,
            )

        if not skip_embed:
            # Embed server (small model — always offload same as LLM)
            embed_model = str(MODELS_DIR / EMBED_GGUF_FILE)
            embed_log = open(str(logs_dir / "embed_server.log"), "w")  # noqa: SIM115
            subprocess.Popen(
                [
                    llama_exe, "-m", embed_model,
                    "--port", str(EMBED_PORT),
                    "--embedding",
                    "--n-gpu-layers", n_gpu_layers,
                ],
                stdout=embed_log,
                stderr=embed_log,
                creationflags=CREATION_FLAGS,
            )
        return True
    except Exception as e:
        log(f"Warning: could not start llama-server: {e}")
        if llm_log is not None:
            llm_log.close()
        if embed_log is not None:
            embed_log.close()
        return False


def get_token() -> dict:
    """Read API_TOKEN from backend/.env for extension auto-configuration."""
    env_path = str(BACKEND_DIR / ".env")
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
    """Start llama-server instances, skipping any that are already running."""
    # Kill leftover Ollama processes to avoid port conflicts on upgrade
    kill_legacy_ollama()

    llm_running = is_port_listening(LLM_PORT)
    embed_running = is_port_listening(EMBED_PORT)

    if llm_running and embed_running:
        log("start_llm: both servers already running")
        return {"ok": True, "status": "already_running"}

    ok = _start_llama_servers(skip_llm=llm_running, skip_embed=embed_running)
    if ok:
        return {"ok": True, "status": "starting"}
    return {"ok": False, "error": "Failed to start llama-server"}


def stop_backend() -> dict:
    """Stop the backend and llama-server (symmetric with start_backend which starts both)."""
    pids = find_pids_on_port(BACKEND_PORT)
    if not pids:
        log("stop_backend: no process found on port 8765")
    else:
        log(f"stop_backend: killing PIDs {pids}")
        kill_pids(pids)

    log("stop_backend: also killing llama-server (symmetric with start_backend)")
    kill_llama_server()

    return {"ok": True, "status": "stopped", "pids": pids if pids else [], "llm_stopped": True}


def stop_llm() -> dict:
    """Stop llama-server processes."""
    log("stop_llm: killing llama-server.exe")
    kill_llama_server()
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
