"""Shared process management utilities for llama-server lifecycle.

Centralises constants (ports, paths, model filenames) and helpers
(port detection, process kill, GPU auto-tune) used by both
``native_host.py`` (sync, pre-backend startup) and ``health.py``
(async, during backend operation).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# -- Path constants ----------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR.parent
BUNDLED_LLAMA_SERVER = APP_DIR / "tools" / "llama-server.exe"
MODELS_DIR = APP_DIR / "models"

# -- Port constants ----------------------------------------------------------

LLM_PORT = 11435
EMBED_PORT = 11436
BACKEND_PORT = 8765

# -- Model filename constants -----------------------------------------------

EMBED_GGUF_FILE = "nomic-embed-text-v1.5.f16.gguf"

# -- Platform flags ----------------------------------------------------------

CREATION_FLAGS: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# -- Port / PID helpers ------------------------------------------------------


def find_pids_on_port(port: int) -> list[int]:
    """Parse ``netstat -ano -p TCP`` to find PIDs listening on *port*."""
    try:
        output = subprocess.check_output(
            ["netstat", "-ano", "-p", "TCP"],
            text=True,
            creationflags=CREATION_FLAGS,
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


def is_port_listening(port: int) -> bool:
    """Check if any process is listening on the given port."""
    return len(find_pids_on_port(port)) > 0


def kill_pids(pids: list[int]) -> None:
    """Kill specific PIDs using taskkill."""
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATION_FLAGS,
            )
        except Exception:
            logger.warning("Failed to kill PID %d", pid)


def kill_pids_on_port(port: int) -> list[int]:
    """Kill all processes listening on *port*. Returns killed PIDs."""
    pids = find_pids_on_port(port)
    kill_pids(pids)
    return pids


def kill_legacy_ollama() -> None:
    """Kill leftover Ollama processes to avoid port conflicts on upgrade."""
    for exe in ("ollama.exe", "ollama_llama_server.exe"):
        try:
            subprocess.run(
                ["taskkill", "/IM", exe, "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATION_FLAGS,
            )
        except Exception:
            pass


def kill_llama_server() -> None:
    """Kill llama-server processes on ports 11435 and 11436 (port-targeted).

    Uses find_pids_on_port() instead of ``taskkill /IM`` to avoid killing
    unrelated llama-server processes that might be running on other ports.
    """
    pids_llm = find_pids_on_port(LLM_PORT)
    pids_embed = find_pids_on_port(EMBED_PORT)
    all_pids = sorted(set(pids_llm + pids_embed))
    if all_pids:
        logger.info("Killing llama-server PIDs %s on ports %d/%d", all_pids, LLM_PORT, EMBED_PORT)
        kill_pids(all_pids)


# -- GPU auto-tune -----------------------------------------------------------


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
        return float(stat.ullTotalPhys) / (1024 ** 3)
    except Exception:
        return 0.0


def _get_dedicated_vram_gb() -> float:
    """Get dedicated GPU VRAM in GB.

    Uses registry first (accurate for all VRAM sizes), falls back to
    Get-CimInstance (capped at 4 GB due to uint32 overflow).
    """
    try:
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
            creationflags=CREATION_FLAGS,
            timeout=5,
        ).strip()
        if output and output.isdigit() and int(output) > 0:
            return int(output) / (1024 ** 3)
    except Exception:
        pass

    try:
        output = subprocess.check_output(
            [
                "powershell.exe", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_VideoController | "
                "Sort-Object AdapterRAM -Descending | "
                "Select-Object -First 1).AdapterRAM",
            ],
            text=True,
            creationflags=CREATION_FLAGS,
            timeout=5,
        ).strip()
        if output and output.isdigit():
            return int(output) / (1024 ** 3)
    except Exception:
        pass

    return 0.0


def detect_gpu_config(
    log_fn: Callable[[str], object] | None = None,
) -> tuple[str, str]:
    """Auto-detect system specs and calculate optimal llama-server settings.

    Reads version.json (GPU type from installer) + live system specs.
    Returns (n_gpu_layers, ctx_size) as strings for command-line args.

    *log_fn* is an optional callable(str) for logging (used by native_host
    which has its own file-based logger).
    """
    def _log(msg: str) -> None:
        if log_fn is not None:
            log_fn(msg)
        else:
            logger.info(msg)

    version_file = APP_DIR / "version.json"
    backend = "cpu"
    gpu_name = ""
    try:
        data = json.loads(version_file.read_text(encoding="utf-8"))
        backend = data.get("llama_backend", "cpu")
        gpu_name = data.get("gpu_detected", "")
    except Exception as e:
        _log(f"Auto-tune: could not read version.json: {e}")

    gpu_lower = gpu_name.lower()
    total_ram = _get_system_ram_gb()
    dedicated_vram = _get_dedicated_vram_gb()

    is_integrated = (
        "radeon graphics" in gpu_lower
        or "radeon(tm) graphics" in gpu_lower
        or "radeon vega" in gpu_lower
        or ("intel" in gpu_lower and "arc" not in gpu_lower)
    )

    _log(
        f"Auto-tune: ram={total_ram:.1f}GB, vram={dedicated_vram:.1f}GB, "
        f"backend={backend}, gpu={gpu_name}, integrated={is_integrated}"
    )

    if backend == "cpu":
        ctx = "4096" if total_ram >= 16 else "2048"
        _log(f"Auto-tune result: ngl=0, ctx={ctx} (CPU-only build)")
        return ("0", ctx)

    if total_ram < 12:
        _log(f"Auto-tune result: ngl=0, ctx=2048 (low RAM: {total_ram:.0f}GB)")
        return ("0", "2048")

    if not is_integrated:
        if dedicated_vram >= 8:
            ctx = "8192" if total_ram >= 24 else "4096"
            _log(f"Auto-tune result: ngl=-1, ctx={ctx} (discrete GPU, {dedicated_vram:.0f}GB VRAM)")
            return ("-1", ctx)
        elif dedicated_vram >= 4:
            _log(f"Auto-tune result: ngl=20, ctx=4096 (discrete GPU, {dedicated_vram:.0f}GB VRAM)")
            return ("20", "4096")
        else:
            _log(
                f"Auto-tune result: ngl=10, ctx=4096 "
                f"(discrete GPU, low VRAM: {dedicated_vram:.0f}GB)"
            )
            return ("10", "4096")

    if total_ram >= 24:
        _log(f"Auto-tune result: ngl=15, ctx=4096 (iGPU, {total_ram:.0f}GB RAM)")
        return ("15", "4096")
    elif total_ram >= 16:
        _log(f"Auto-tune result: ngl=10, ctx=4096 (iGPU, {total_ram:.0f}GB RAM)")
        return ("10", "4096")
    else:
        _log(f"Auto-tune result: ngl=0, ctx=2048 (iGPU, limited RAM: {total_ram:.0f}GB)")
        return ("0", "2048")


def resolve_llama_exe() -> str:
    """Return path to llama-server executable (bundled or on PATH)."""
    return str(BUNDLED_LLAMA_SERVER) if BUNDLED_LLAMA_SERVER.exists() else "llama-server"
