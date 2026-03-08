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

    # Check if backend is already running on port 8765
    if _is_port_listening(8765):
        log("start_backend: port 8765 already in use, backend likely running")
        return {"ok": False, "error": "Backend already running on port 8765."}

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
                [venv_python, "-m", "uvicorn", "app.main:app",
                 "--host", "127.0.0.1", "--port", "8765"],
                cwd=BACKEND_DIR,
                stdout=fout,
                stderr=ferr,
                creationflags=_CREATION_FLAGS,
            )
        log(f"Started PID={proc.pid}")
        return {
            "ok": True, "status": "starting",
            "pid": proc.pid, "llm_started": llm_started,
        }
    except Exception as e:
        log(f"Error starting backend: {e}")
        return {"ok": False, "error": str(e)}


def _get_system_ram_gb() -> float:
    """Get total system RAM in GB using Windows kernel32 API."""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        return 0.0


def _get_dedicated_vram_gb() -> float:
    """Get dedicated GPU VRAM in GB.

    Uses Get-CimInstance (the modern CIM replacement for deprecated WMI).
    Get-CimInstance is fully supported on Windows 11 25H2+ — only the old
    Get-WmiObject cmdlet was deprecated, not the underlying CIM infrastructure.
    Falls back to 0 if detection fails.

    Note: CIM's AdapterRAM is a uint32 that overflows at 4 GB. For GPUs with
    ≥4 GB VRAM, we detect the overflow and use qwMemorySize from the registry.
    """
    try:
        # Try registry first — accurate for all VRAM sizes (no uint32 overflow)
        output = subprocess.check_output(
            [
                "powershell.exe", "-NoProfile", "-Command",
                "$adapters = Get-ItemProperty 'HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\"
                "{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' -EA SilentlyContinue; "
                "$best = $adapters | Sort-Object { "
                "  if ($_.HardwareInformation.qwMemorySize) { $_.HardwareInformation.qwMemorySize } "
                "  elseif ($_.'HardwareInformation.qwMemorySize') { $_.'HardwareInformation.qwMemorySize' } "
                "  else { 0 } "
                "} -Descending | Select-Object -First 1; "
                "$v = $best.'HardwareInformation.qwMemorySize'; "
                "if ($v) { $v } else { 0 }",
            ],
            text=True,
            creationflags=_CREATION_FLAGS,
            timeout=5,
        ).strip()
        if output and output.isdigit() and int(output) > 0:
            vram_bytes = int(output)
            return vram_bytes / (1024 ** 3)
    except Exception as e:
        log(f"VRAM detection (registry) failed: {e}")

    # Fallback: Get-CimInstance (works but capped at 4 GB due to uint32)
    try:
        output = subprocess.check_output(
            [
                "powershell.exe", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_VideoController | "
                "Sort-Object AdapterRAM -Descending | "
                "Select-Object -First 1).AdapterRAM",
            ],
            text=True,
            creationflags=_CREATION_FLAGS,
            timeout=5,
        ).strip()
        if output and output.isdigit():
            return int(output) / (1024 ** 3)
    except Exception as e:
        log(f"VRAM detection (CIM fallback) failed: {e}")

    return 0.0


def _detect_gpu_config() -> tuple[str, str]:
    """Auto-detect system specs and calculate optimal llama-server settings.

    Reads version.json (GPU type from installer) + live system specs (RAM, VRAM).
    Returns (n_gpu_layers, ctx_size) as strings for command-line args.

    Strategy:
      - Discrete GPU with ≥6 GB VRAM: full offload, large context
      - Discrete GPU with <6 GB VRAM: partial offload
      - Integrated GPU (AMD APU, Intel UHD): partial offload using iGPU compute
      - CPU-only or <12 GB RAM: no GPU offload, conservative context
    """
    version_file = os.path.join(APP_DIR, "version.json")
    backend = "cpu"
    gpu_name = ""
    try:
        with open(version_file, encoding="utf-8") as f:
            data = json.loads(f.read())
        backend = data.get("llama_backend", "cpu")
        gpu_name = data.get("gpu_detected", "")
    except Exception as e:
        log(f"Auto-tune: could not read version.json: {e}")

    gpu_lower = gpu_name.lower()
    total_ram = _get_system_ram_gb()
    dedicated_vram = _get_dedicated_vram_gb()

    # Detect integrated GPUs (shared system RAM, no dedicated VRAM)
    is_integrated = (
        "radeon graphics" in gpu_lower
        or "radeon(tm) graphics" in gpu_lower
        or "radeon vega" in gpu_lower
        or ("intel" in gpu_lower and "arc" not in gpu_lower)
    )

    log(
        f"Auto-tune: ram={total_ram:.1f}GB, vram={dedicated_vram:.1f}GB, "
        f"backend={backend}, gpu={gpu_name}, integrated={is_integrated}"
    )

    # CPU-only build — no GPU offload possible
    if backend == "cpu":
        ctx = "4096" if total_ram >= 16 else "2048"
        log(f"Auto-tune result: ngl=0, ctx={ctx} (CPU-only build)")
        return ("0", ctx)

    # Low RAM systems — be conservative
    if total_ram < 12:
        log(f"Auto-tune result: ngl=0, ctx=2048 (low RAM: {total_ram:.0f}GB)")
        return ("0", "2048")

    # Discrete GPU with dedicated VRAM
    if not is_integrated:
        if dedicated_vram >= 8:
            ctx = "8192" if total_ram >= 24 else "4096"
            log(f"Auto-tune result: ngl=-1, ctx={ctx} (discrete GPU, {dedicated_vram:.0f}GB VRAM)")
            return ("-1", ctx)
        elif dedicated_vram >= 4:
            log(f"Auto-tune result: ngl=20, ctx=4096 (discrete GPU, {dedicated_vram:.0f}GB VRAM)")
            return ("20", "4096")
        else:
            log(f"Auto-tune result: ngl=10, ctx=4096 (discrete GPU, low VRAM: {dedicated_vram:.0f}GB)")
            return ("10", "4096")

    # Integrated GPU — use partial offload to leverage iGPU compute
    if total_ram >= 24:
        log(f"Auto-tune result: ngl=15, ctx=4096 (iGPU, {total_ram:.0f}GB RAM)")
        return ("15", "4096")
    elif total_ram >= 16:
        log(f"Auto-tune result: ngl=10, ctx=4096 (iGPU, {total_ram:.0f}GB RAM)")
        return ("10", "4096")
    else:
        log(f"Auto-tune result: ngl=0, ctx=2048 (iGPU, limited RAM: {total_ram:.0f}GB)")
        return ("0", "2048")


def _start_llama_servers(
    *, skip_llm: bool = False, skip_embed: bool = False,
) -> bool:
    """Start LLM and/or embed llama-server instances.

    Args:
        skip_llm: If True, skip starting the LLM server (already running).
        skip_embed: If True, skip starting the embed server (already running).
    """
    llama_exe = LLAMA_SERVER_EXE if os.path.exists(LLAMA_SERVER_EXE) else "llama-server"
    log(f"Starting llama-server instances: {llama_exe} (skip_llm={skip_llm}, skip_embed={skip_embed})")

    n_gpu_layers, ctx_size = _detect_gpu_config()
    logs_dir = os.path.join(APP_DIR, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    llm_log = None
    embed_log = None
    try:
        if not skip_llm:
            # LLM server
            llm_model = os.path.join(MODELS_DIR, "Qwen3.5-9B-Q4_K_M.gguf")
            llm_log = open(os.path.join(logs_dir, "llm_server.log"), "w")  # noqa: SIM115
            subprocess.Popen(
                [
                    llama_exe, "-m", llm_model,
                    "--port", "11435",
                    "--n-gpu-layers", n_gpu_layers,
                    "--ctx-size", ctx_size,
                ],
                stdout=llm_log,
                stderr=llm_log,
                creationflags=_CREATION_FLAGS,
            )

        if not skip_embed:
            # Embed server (small model — always offload same as LLM)
            embed_model = os.path.join(MODELS_DIR, "nomic-embed-text-v1.5.f16.gguf")
            embed_log = open(os.path.join(logs_dir, "embed_server.log"), "w")  # noqa: SIM115
            subprocess.Popen(
                [
                    llama_exe, "-m", embed_model,
                    "--port", "11436",
                    "--embedding",
                    "--n-gpu-layers", n_gpu_layers,
                ],
                stdout=embed_log,
                stderr=embed_log,
                creationflags=_CREATION_FLAGS,
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
    """Start llama-server instances, skipping any that are already running."""
    # Kill leftover Ollama processes to avoid port conflicts on upgrade
    _kill_legacy_ollama()

    llm_running = _is_port_listening(11435)
    embed_running = _is_port_listening(11436)

    if llm_running and embed_running:
        log("start_llm: both servers already running")
        return {"ok": True, "status": "already_running"}

    ok = _start_llama_servers(skip_llm=llm_running, skip_embed=embed_running)
    if ok:
        return {"ok": True, "status": "starting"}
    return {"ok": False, "error": "Failed to start llama-server"}


def _kill_pids(pids: list[int]) -> None:
    """Kill specific PIDs using taskkill."""
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATION_FLAGS,
            )
        except Exception as e:
            log(f"_kill_pids: failed to kill PID {pid}: {e}")


def _kill_llm() -> None:
    """Kill llama-server processes on ports 11435 and 11436 (port-targeted).

    Uses _find_pids_on_port() instead of ``taskkill /IM`` to avoid killing
    unrelated llama-server processes that might be running on other ports.
    """
    pids_llm = _find_pids_on_port(11435)
    pids_embed = _find_pids_on_port(11436)
    all_pids = sorted(set(pids_llm + pids_embed))
    if all_pids:
        log(f"_kill_llm: killing PIDs {all_pids} on ports 11435/11436")
        _kill_pids(all_pids)
    else:
        log("_kill_llm: no llama-server PIDs found on ports 11435/11436")


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
