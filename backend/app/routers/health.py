import asyncio
import os
import signal
import subprocess
import sys

import httpx
from fastapi import APIRouter, Request

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request) -> dict[str, object]:
    """Return system health status including Ollama and ChromaDB state."""
    ollama_reachable = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            ollama_reachable = resp.status_code == 200
    except Exception:
        ollama_reachable = False

    chroma_ready = False
    chroma_doc_counts: dict[str, int] = {}
    try:
        chroma_client = request.app.state.chroma_client
        collections = chroma_client.list_collections()
        chroma_ready = True
        for col in collections:
            chroma_doc_counts[col.name] = col.count()
    except Exception:
        chroma_ready = False

    return {
        "status": "ok" if ollama_reachable and chroma_ready else "degraded",
        "ollama_reachable": ollama_reachable,
        "chroma_ready": chroma_ready,
        "chroma_doc_counts": chroma_doc_counts,
        "version": settings.version,
    }


@router.post("/shutdown")
async def shutdown_backend() -> dict[str, str]:
    """Gracefully shut down the backend server after a short delay."""

    async def _delayed_kill() -> None:
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_delayed_kill())
    return {"status": "shutting_down"}


@router.post("/ollama/start")
async def start_ollama() -> dict[str, str]:
    """Start the Ollama server as a detached background process."""
    # Check if already running
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
            if resp.status_code == 200:
                return {"status": "already_running"}
    except Exception:
        pass

    if sys.platform == "win32":
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return {"status": "starting"}


@router.post("/ollama/stop")
async def stop_ollama() -> dict[str, str]:
    """Stop the Ollama server process."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/IM", "ollama.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        subprocess.run(
            ["taskkill", "/IM", "ollama_llama_server.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        subprocess.run(["pkill", "-f", "ollama"], check=False)
    return {"status": "stopping"}
