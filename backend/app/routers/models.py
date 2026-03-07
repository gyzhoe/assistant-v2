import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.constants import EMBED_MODEL_PREFIXES, MODEL_DISPLAY_NAMES

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

    return {"models": available, "current": current}
