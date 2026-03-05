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

# Derive app install directory (backend/ -> app root) for bundled Ollama path.
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_APP_DIR = _BACKEND_DIR.parent
_BUNDLED_OLLAMA = _APP_DIR / "tools" / "ollama.exe"
_OLLAMA_RUNNERS_DIR = _APP_DIR / "tools" / "lib" / "ollama"

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


@router.get("/health")
async def health_check(request: Request) -> dict[str, object]:
    """Return minimal health status. Detailed info available at /health/detail."""
    return {"status": "ok"}


@router.get("/health/detail", dependencies=[Depends(_require_token)])
async def health_detail(request: Request) -> dict[str, object]:
    """Return detailed system health status including Ollama and ChromaDB state."""
    ollama_reachable = False
    try:
        llm_client = request.app.state.llm_service.client
        resp = await llm_client.get("/api/tags", timeout=5.0)
        ollama_reachable = resp.status_code == 200
    except Exception:
        ollama_reachable = False

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
        "status": "ok" if ollama_reachable and chroma_ready else "degraded",
        "ollama_reachable": ollama_reachable,
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


@router.post("/ollama/start", dependencies=[Depends(_require_token), Depends(_require_localhost)])
async def start_ollama(request: Request) -> dict[str, str]:
    """Start the Ollama server as a detached background process."""

    # Check if already running
    try:
        llm_client = request.app.state.llm_service.client
        resp = await llm_client.get("/api/tags", timeout=3.0)
        if resp.status_code == 200:
            return {"status": "already_running"}
    except Exception:
        pass

    cmd: list[str] = (
        [str(_BUNDLED_OLLAMA), "serve"]
        if _BUNDLED_OLLAMA.exists()
        else ["ollama", "serve"]
    )
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "127.0.0.1:11435"
    env["OLLAMA_VULKAN"] = "1"
    if _OLLAMA_RUNNERS_DIR.is_dir():
        env["OLLAMA_RUNNERS_DIR"] = str(_OLLAMA_RUNNERS_DIR)

    creation_flags: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        env=env,
    )
    return {"status": "starting"}


@router.post("/ollama/stop", dependencies=[Depends(_require_token), Depends(_require_localhost)])
async def stop_ollama(request: Request) -> dict[str, str]:
    """Stop the Ollama server process."""

    if sys.platform == "win32":
        await asyncio.to_thread(
            subprocess.run,
            ["taskkill", "/IM", "ollama.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        await asyncio.to_thread(
            subprocess.run,
            ["taskkill", "/IM", "ollama_llama_server.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        await asyncio.to_thread(subprocess.run, ["pkill", "-f", "ollama"], check=False)
    return {"status": "stopping"}
