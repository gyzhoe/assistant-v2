import json

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["models"])


@router.get("/models")
async def list_models(request: Request) -> dict[str, list[str]]:
    """Proxy Ollama's /api/tags to return available model names."""
    try:
        client = request.app.state.llm_service._client
        resp = await client.get("/api/tags", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        model_names = [m["name"] for m in data.get("models", [])]
        return {"models": model_names}
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": "Cannot reach Ollama to list models.", "error_code": "OLLAMA_DOWN"},
        ) from exc
