import json

import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings

router = APIRouter(tags=["models"])


@router.get("/models")
async def list_models() -> dict[str, list[str]]:
    """Proxy Ollama's /api/tags to return available model names."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            model_names = [m["name"] for m in data.get("models", [])]
            return {"models": model_names}
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": "Cannot reach Ollama to list models.", "error_code": "OLLAMA_DOWN"},
        ) from exc
