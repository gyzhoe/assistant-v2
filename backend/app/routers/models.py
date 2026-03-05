import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["models"])

# Model families that are embedding-only and should not appear in the
# generate dropdown.  Ollama exposes ``details.family`` in /api/tags.
_EMBEDDING_ONLY_FAMILIES: frozenset[str] = frozenset({"nomic-bert", "bert"})


def _is_generate_model(model: dict[str, Any]) -> bool:
    """Return *True* when the model can be used for text generation.

    Embedding-only models (e.g. ``nomic-embed-text``) are excluded based on
    the ``details.family`` metadata returned by Ollama.
    """
    family: str = model.get("details", {}).get("family", "")
    return family.lower() not in _EMBEDDING_ONLY_FAMILIES


@router.get("/models")
async def list_models(request: Request) -> dict[str, list[str]]:
    """Proxy Ollama's /api/tags to return available model names."""
    try:
        client = request.app.state.llm_service.client
        resp = await client.get("/api/tags", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        model_names = [
            m["name"] for m in data.get("models", []) if _is_generate_model(m)
        ]
        return {"models": model_names}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Ollama returned HTTP {exc.response.status_code} while listing models.",
                "error_code": "MODEL_ERROR",
            },
        ) from exc
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": "Cannot reach Ollama to list models.", "error_code": "OLLAMA_DOWN"},
        ) from exc
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": "Cannot reach Ollama to list models.", "error_code": "OLLAMA_DOWN"},
        ) from exc
