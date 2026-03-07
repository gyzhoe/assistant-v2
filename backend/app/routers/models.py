import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.constants import EMBED_MODEL_PREFIXES, GGUF_MODELS, MODEL_DISPLAY_NAMES
from app.models.request_models import DownloadModelsRequest
from app.services.model_download_service import ModelDownloadService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])

_MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"


def _gguf_display_name(filename: str) -> str:
    """Map a GGUF filename to a display name, falling back to lowercase stem."""
    if filename in MODEL_DISPLAY_NAMES:
        return MODEL_DISPLAY_NAMES[filename]
    return filename.removesuffix(".gguf").lower()


def scan_models() -> list[str]:
    """Scan the models directory for available GGUF files, excluding embed models."""
    if not _MODELS_DIR.is_dir():
        return []
    names: list[str] = []
    for path in sorted(_MODELS_DIR.glob("*.gguf")):
        if any(path.name.startswith(prefix) for prefix in EMBED_MODEL_PREFIXES):
            continue
        names.append(_gguf_display_name(path.name))
    return names


def _build_model_info() -> dict[str, dict[str, object]]:
    """Build model_info dict for non-embed GGUF models."""
    info: dict[str, dict[str, object]] = {}
    for model in GGUF_MODELS:
        if model.is_embed:
            continue
        dest = _MODELS_DIR / model.name
        downloaded = dest.is_file() and dest.stat().st_size > 0
        size_bytes: int | None = dest.stat().st_size if downloaded else None
        info[model.display_name] = {
            "downloaded": downloaded,
            "size_bytes": size_bytes,
            "description": model.description,
            "gguf_name": model.name,
        }
    return info


@router.get("/models")
async def list_models(request: Request) -> dict[str, object]:
    """Return available models and which one is currently loaded."""
    try:
        client = request.app.state.llm_service.client
        resp = await client.get("/health", timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"LLM server returned HTTP {exc.response.status_code} while checking health.",
                "error_code": "MODEL_ERROR",
            },
        ) from exc
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": "Cannot reach LLM server.", "error_code": "LLM_DOWN"},
        ) from exc

    available = scan_models()
    if not available:
        available = [settings.default_model]

    current: str = getattr(request.app.state, "current_llm_model", settings.default_model)

    return {
        "models": available,
        "current": current,
        "model_info": _build_model_info(),
    }


def _get_download_service(request: Request) -> ModelDownloadService:
    svc: ModelDownloadService | None = getattr(
        request.app.state, "model_download_service", None
    )
    if svc is None:
        raise HTTPException(status_code=503, detail="Download service not initialized")
    return svc


@router.post("/models/download")
async def start_download(
    request: Request,
    body: DownloadModelsRequest,
) -> dict[str, object]:
    """Start downloading GGUF models. Empty list = all missing non-embed models."""
    svc = _get_download_service(request)

    model_names = body.models
    if not model_names:
        # Download all missing non-embed models
        model_names = [
            m.name
            for m in GGUF_MODELS
            if not m.is_embed
            and not (_MODELS_DIR / m.name).is_file()
        ]
        if not model_names:
            return {"status": "all_downloaded", "models": []}

    result = svc.start_download(model_names, _MODELS_DIR)
    return result


@router.get("/models/download/status")
async def download_status(request: Request) -> dict[str, object]:
    """Return current download progress."""
    svc = _get_download_service(request)
    return svc.get_status()


@router.post("/models/download/cancel")
async def cancel_download(request: Request) -> dict[str, str]:
    """Cancel the current download."""
    svc = _get_download_service(request)
    return svc.cancel()
