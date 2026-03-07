import asyncio
import logging
import os
import secrets
import signal
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from app.config import settings
from app.services.audit import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Derive app install directory (backend/ -> app root) for bundled llama-server path.
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_APP_DIR = _BACKEND_DIR.parent
_BUNDLED_LLAMA_SERVER = _APP_DIR / "tools" / "llama-server.exe"
_MODELS_DIR = _APP_DIR / "models"

_token_header = APIKeyHeader(name="X-Extension-Token", auto_error=False)

_LOCALHOST_HOSTS = {"127.0.0.1", "::1"}


async def _require_token(token: str | None = Depends(_token_header)) -> None:
    """Guard for destructive endpoints — requires token even when api_token is empty."""
    if not settings.api_token:
        # No token configured (dev mode) — allow through
        return
    if not token or not secrets.compare_digest(token, settings.api_token):
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _require_localhost(request: Request) -> None:
    """Restrict process-control endpoints to loopback connections only."""
    client = request.client
    if client is None or client.host not in _LOCALHOST_HOSTS:
        raise HTTPException(status_code=403, detail="Process control is only available from localhost.")


async def _kill_legacy_ollama() -> None:
    """Kill leftover Ollama processes to avoid port conflicts on upgrade."""
    if sys.platform == "win32":
        for exe in ("ollama.exe", "ollama_llama_server.exe"):
            await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/IM", exe, "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    else:
        await asyncio.to_thread(subprocess.run, ["pkill", "-f", "ollama"], check=False)


@router.get("/health")
async def health_check(request: Request) -> dict[str, object]:
    """Return minimal health status. Detailed info available at /health/detail."""
    return {"status": "ok"}


@router.get("/health/detail", dependencies=[Depends(_require_token)])
async def health_detail(request: Request) -> dict[str, object]:
    """Return detailed system health status including LLM, embed, and ChromaDB state."""
    llm_reachable = False
    try:
        llm_client = request.app.state.llm_service.client
        resp = await llm_client.get("/health", timeout=5.0)
        llm_reachable = resp.status_code == 200
    except Exception:
        llm_reachable = False

    embed_reachable = False
    try:
        embed_client = request.app.state.embed_service._client
        if hasattr(embed_client, "get"):
            resp = await embed_client.get("/health", timeout=5.0)
            embed_reachable = resp.status_code == 200
    except Exception:
        embed_reachable = False

    chroma_ready = False
    chroma_doc_counts: dict[str, int] = {}
    try:
        chroma_client = request.app.state.chroma_client
        collections = await asyncio.to_thread(chroma_client.list_collections)
        chroma_ready = True
        for col in collections:
            chroma_doc_counts[col.name] = await asyncio.to_thread(col.count)
    except Exception:
        chroma_ready = False

    return {
        "status": "ok" if llm_reachable and embed_reachable and chroma_ready else "degraded",
        "llm_reachable": llm_reachable,
        "embed_reachable": embed_reachable,
        "chroma_ready": chroma_ready,
        "chroma_doc_counts": chroma_doc_counts,
        "version": settings.version,
    }


@router.post("/shutdown", dependencies=[Depends(_require_token), Depends(_require_localhost)])
async def shutdown_backend(request: Request) -> dict[str, str]:
    """Gracefully shut down the backend server after a short delay."""

    client_ip = request.client.host if request.client else ""
    audit_log("shutdown", client_ip=client_ip)

    async def _delayed_kill() -> None:
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_delayed_kill())
    return {"status": "shutting_down"}


@router.post("/llm/start", dependencies=[Depends(_require_token), Depends(_require_localhost)])
async def start_llm(request: Request) -> dict[str, str]:
    """Start the llama-server processes as detached background processes."""

    # Check if LLM server already running
    try:
        llm_client = request.app.state.llm_service.client
        resp = await llm_client.get("/health", timeout=3.0)
        if resp.status_code == 200:
            return {"status": "already_running"}
    except Exception:
        pass

    # Kill any leftover Ollama processes to avoid port conflicts on upgrade
    await _kill_legacy_ollama()

    llama_exe = (
        str(_BUNDLED_LLAMA_SERVER)
        if _BUNDLED_LLAMA_SERVER.exists()
        else "llama-server"
    )

    creation_flags: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # Start LLM server
    llm_model = _MODELS_DIR / "Qwen3.5-9B-Q4_K_M.gguf"
    subprocess.Popen(
        [
            llama_exe, "-m", str(llm_model),
            "--port", "11435",
            "--n-gpu-layers", "-1",
            "--ctx-size", "8192",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    # Start embed server
    embed_model = _MODELS_DIR / "nomic-embed-text-v1.5.f16.gguf"
    subprocess.Popen(
        [
            llama_exe, "-m", str(embed_model),
            "--port", "11436",
            "--embedding",
            "--n-gpu-layers", "-1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    return {"status": "starting"}


@router.post("/llm/stop", dependencies=[Depends(_require_token), Depends(_require_localhost)])
async def stop_llm(request: Request) -> dict[str, str]:
    """Stop the llama-server processes."""

    if sys.platform == "win32":
        await asyncio.to_thread(
            subprocess.run,
            ["taskkill", "/IM", "llama-server.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        await asyncio.to_thread(subprocess.run, ["pkill", "-f", "llama-server"], check=False)
    return {"status": "stopping"}
