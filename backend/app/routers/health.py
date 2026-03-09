import asyncio
import logging
import os
import secrets
import signal
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from app.config import settings
from app.constants import MODEL_DISPLAY_NAMES, MODEL_GGUF_FILES
from app.models.request_models import SwitchModelRequest
from app.process_utils import (
    CREATION_FLAGS,
    EMBED_GGUF_FILE,
    EMBED_PORT,
    LLM_PORT,
    MODELS_DIR,
    detect_gpu_config,
    is_port_listening,
    kill_legacy_ollama,
    kill_pids_on_port,
    resolve_llama_exe,
)
from app.services.audit import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_process_lock = asyncio.Lock()
_legacy_ollama_checked = False


async def _check_legacy_ollama() -> None:
    """Kill leftover Ollama processes once, then skip on subsequent calls."""
    global _legacy_ollama_checked  # noqa: PLW0603
    await asyncio.to_thread(kill_legacy_ollama)
    _legacy_ollama_checked = True


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
    """Return detailed system health status including LLM, embed, and ChromaDB state."""

    async def _probe_llm() -> bool:
        try:
            llm_client = request.app.state.llm_service.client
            resp = await llm_client.get("/health", timeout=5.0)
            return bool(resp.status_code == 200)
        except Exception:
            return False

    async def _probe_embed() -> bool:
        try:
            embed_client = request.app.state.embed_service.client
            if hasattr(embed_client, "get"):
                resp = await embed_client.get("/health", timeout=5.0)
                return bool(resp.status_code == 200)
            return False
        except Exception:
            return False

    async def _probe_chroma() -> tuple[bool, dict[str, int]]:
        try:
            chroma_client = request.app.state.chroma_client
            collections = await asyncio.to_thread(
                chroma_client.list_collections,
            )
            count_tasks = [asyncio.to_thread(col.count) for col in collections]
            results = await asyncio.gather(*count_tasks)
            counts = dict(zip(
                [c.name for c in collections], results,
            ))
            return True, counts
        except Exception:
            return False, {}

    llm_reachable, embed_reachable, (chroma_ready, chroma_doc_counts) = (
        await asyncio.gather(_probe_llm(), _probe_embed(), _probe_chroma())
    )

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
    """Start the llama-server processes as detached background processes.

    Checks each server independently so the embed server is not restarted
    if it is already running (and vice versa).
    """
    async with _process_lock:
        llm_running = False
        embed_running = False

        # Check if LLM server is already healthy
        try:
            llm_client = request.app.state.llm_service.client
            resp = await llm_client.get("/health", timeout=3.0)
            llm_running = resp.status_code == 200
        except Exception:
            pass

        # Check if embed server is already listening
        embed_running = await asyncio.to_thread(is_port_listening, EMBED_PORT)

        if llm_running and embed_running:
            return {"status": "already_running"}

        # Kill any leftover Ollama processes to avoid port conflicts
        if not _legacy_ollama_checked:
            await _check_legacy_ollama()

        llama_exe = resolve_llama_exe()
        n_gpu_layers, ctx_size = await asyncio.to_thread(detect_gpu_config)

        if not llm_running:
            # Kill stale process on LLM port if any
            if await asyncio.to_thread(is_port_listening, LLM_PORT):
                await asyncio.to_thread(kill_pids_on_port, LLM_PORT)
                await asyncio.sleep(0.3)

            # Start LLM server — resolve GGUF from current model or default
            current_display: str = getattr(
                request.app.state, "current_llm_model", settings.default_model,
            )
            gguf_name = MODEL_GGUF_FILES.get(
                current_display,
                MODEL_GGUF_FILES.get(settings.default_model, ""),
            )
            llm_model = (
                MODELS_DIR / gguf_name if gguf_name
                else MODELS_DIR / MODEL_GGUF_FILES[settings.default_model]
            )
            subprocess.Popen(
                [
                    llama_exe, "-m", str(llm_model),
                    "--port", str(LLM_PORT),
                    "--n-gpu-layers", n_gpu_layers,
                    "--ctx-size", ctx_size,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATION_FLAGS,
            )

        if not embed_running:
            # Kill stale process on embed port if any
            if await asyncio.to_thread(is_port_listening, EMBED_PORT):
                await asyncio.to_thread(kill_pids_on_port, EMBED_PORT)
                await asyncio.sleep(0.3)

            embed_model = MODELS_DIR / EMBED_GGUF_FILE
            subprocess.Popen(
                [
                    llama_exe, "-m", str(embed_model),
                    "--port", str(EMBED_PORT),
                    "--embedding",
                    "--n-gpu-layers", n_gpu_layers,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATION_FLAGS,
            )

        return {"status": "starting"}


@router.post("/llm/stop", dependencies=[Depends(_require_token), Depends(_require_localhost)])
async def stop_llm(request: Request) -> dict[str, str]:
    """Stop the LLM server on port 11435 only. Leaves embed server alive."""
    async with _process_lock:
        killed = await asyncio.to_thread(kill_pids_on_port, LLM_PORT)
        if killed:
            logger.info("Stopped LLM server (PIDs: %s)", killed)
        return {"status": "stopping"}


@router.post("/llm/switch", dependencies=[Depends(_require_token), Depends(_require_localhost)])
async def switch_llm(request: Request, body: SwitchModelRequest) -> dict[str, str]:
    """Switch the LLM model by restarting llama-server with a different GGUF.

    Uses port-targeted kill (port 11435 only) so the embed server on 11436
    is never affected.
    """
    async with _process_lock:
        display_name = body.model

        # Probe the actual running model to detect state mismatch
        current: str = getattr(
            request.app.state, "current_llm_model", settings.default_model,
        )
        actual_model = await _probe_loaded_model(request)
        if actual_model and actual_model != current:
            logger.warning(
                "Model state mismatch: app.state says '%s' but server has '%s'. Correcting.",
                current, actual_model,
            )
            request.app.state.current_llm_model = actual_model
            current = actual_model

        if display_name == current:
            return {"status": "already_loaded", "model": current}

        # Resolve GGUF filename
        gguf_name = MODEL_GGUF_FILES.get(display_name)
        if not gguf_name:
            raise HTTPException(
                status_code=404, detail=f"Unknown model: {display_name}",
            )
        gguf_path = MODELS_DIR / gguf_name
        if not gguf_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Model file not found: {gguf_name}",
            )

        # Kill only the LLM server on port 11435 — leave embed server alone
        await asyncio.to_thread(kill_pids_on_port, LLM_PORT)

        # Brief pause to let the port free up
        await asyncio.sleep(0.5)

        # Auto-tune GPU settings
        llama_exe = resolve_llama_exe()
        n_gpu_layers, ctx_size = await asyncio.to_thread(detect_gpu_config)

        # Start llama-server with the new model
        subprocess.Popen(
            [
                llama_exe, "-m", str(gguf_path),
                "--port", str(LLM_PORT),
                "--n-gpu-layers", n_gpu_layers,
                "--ctx-size", ctx_size,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATION_FLAGS,
        )

        # Update model state AFTER starting the new server
        request.app.state.current_llm_model = display_name
        logger.info("Switched LLM model to %s (%s)", display_name, gguf_name)

        return {"status": "switching", "model": display_name}


async def _probe_loaded_model(request: Request) -> str | None:
    """Probe the LLM server's ``/v1/models`` endpoint to detect the loaded model.

    Returns the display name if detection succeeds, or ``None`` on failure.
    """
    try:
        llm_client = request.app.state.llm_service.client
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


@router.post("/llm/restart", dependencies=[Depends(_require_token), Depends(_require_localhost)])
async def restart_llm(request: Request) -> dict[str, str]:
    """Restart the LLM server on port 11435 with the current model.

    Kills the existing LLM process, waits for the port to free, then starts
    a new instance. The embed server on 11436 is not affected.
    """
    async with _process_lock:
        current_display: str = getattr(
            request.app.state, "current_llm_model", settings.default_model,
        )
        gguf_name = MODEL_GGUF_FILES.get(
            current_display,
            MODEL_GGUF_FILES.get(settings.default_model, ""),
        )
        gguf_path = (
            MODELS_DIR / gguf_name if gguf_name
            else MODELS_DIR / "Qwen3.5-9B-Q4_K_M.gguf"
        )

        # Kill the LLM server on port 11435
        await asyncio.to_thread(kill_pids_on_port, LLM_PORT)

        # Wait for port to free (poll with timeout)
        for _ in range(20):  # ~4 seconds max
            if not await asyncio.to_thread(is_port_listening, LLM_PORT):
                break
            await asyncio.sleep(0.2)

        llama_exe = resolve_llama_exe()
        n_gpu_layers, ctx_size = await asyncio.to_thread(detect_gpu_config)

        subprocess.Popen(
            [
                llama_exe, "-m", str(gguf_path),
                "--port", str(LLM_PORT),
                "--n-gpu-layers", n_gpu_layers,
                "--ctx-size", ctx_size,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATION_FLAGS,
        )

        logger.info("Restarting LLM server with model %s", current_display)
        return {"status": "restarting", "model": current_display}
