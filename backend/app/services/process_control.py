"""Process control helpers for llama-server lifecycle.

Extracted from ``app.routers.health`` to keep route handlers thin.
Houses process-level state (lock, legacy-Ollama flag), server probing,
and the shared ``launch_llama_server()`` subprocess helper.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess

import httpx

from app.constants import MODEL_DISPLAY_NAMES
from app.process_utils import (
    CREATION_FLAGS,
    kill_legacy_ollama,
)

logger = logging.getLogger(__name__)

# -- Process-level state (module singletons) ---------------------------------

_process_lock = asyncio.Lock()
_legacy_ollama_checked = False


async def check_legacy_ollama() -> None:
    """Kill leftover Ollama processes once, then skip on subsequent calls."""
    global _legacy_ollama_checked  # noqa: PLW0603
    await asyncio.to_thread(kill_legacy_ollama)
    _legacy_ollama_checked = True


def is_legacy_ollama_checked() -> bool:
    """Return whether the legacy Ollama check has already run."""
    return _legacy_ollama_checked


# -- Server probing ----------------------------------------------------------


async def probe_loaded_model(llm_client: httpx.AsyncClient) -> str | None:
    """Probe the LLM server's ``/v1/models`` endpoint to detect the loaded model.

    *llm_client* is the httpx ``AsyncClient`` pointing at the LLM server.
    Returns the display name if detection succeeds, or ``None`` on failure.
    """
    try:
        resp = await llm_client.get("/v1/models", timeout=3.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        models_list = data.get("data", [])
        if not models_list:
            return None
        model_id: str = models_list[0].get("id", "")
        # model_id is typically the GGUF filename — map it to display name
        if model_id in MODEL_DISPLAY_NAMES:
            return MODEL_DISPLAY_NAMES[model_id]
        # Also try matching by basename (some servers report full path)
        basename = model_id.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if basename in MODEL_DISPLAY_NAMES:
            return MODEL_DISPLAY_NAMES[basename]
        return None
    except Exception:
        return None


# -- Subprocess launcher -----------------------------------------------------


def launch_llama_server(
    exe: str,
    model_path: str,
    port: int,
    n_gpu_layers: str,
    ctx_size: str | None = None,
    *,
    embedding: bool = False,
) -> subprocess.Popen[bytes]:
    """Start a llama-server subprocess with the given parameters.

    This deduplicates the near-identical ``subprocess.Popen`` blocks that
    were previously scattered across ``start_llm``, ``switch_llm``, and
    ``restart_llm`` in health.py.

    Parameters
    ----------
    exe:
        Path to the llama-server executable.
    model_path:
        Path to the GGUF model file.
    port:
        Port number to bind the server to.
    n_gpu_layers:
        Number of GPU layers (``"-1"`` for all, ``"0"`` for CPU-only).
    ctx_size:
        Context window size.  Omitted from the command line when ``None``
        (useful for the embedding server which does not need ``--ctx-size``).
    embedding:
        If ``True``, add the ``--embedding`` flag.
    """
    cmd: list[str] = [
        exe, "-m", model_path,
        "--port", str(port),
        "--n-gpu-layers", n_gpu_layers,
    ]
    if ctx_size is not None:
        cmd.extend(["--ctx-size", ctx_size])
    if embedding:
        cmd.append("--embedding")

    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATION_FLAGS,
    )
