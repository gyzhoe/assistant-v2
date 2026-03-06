import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import settings

router = APIRouter(tags=["models"])


@router.get("/models")
async def list_models(request: Request) -> dict[str, list[str]]:
    """Return the configured default model.

    Since llama-server loads a single model at a time, we return the
    configured default model name. The LLM server is probed via /health
    to verify it is reachable.
    """
    try:
        client = request.app.state.llm_service.client
        resp = await client.get("/health", timeout=10.0)
        resp.raise_for_status()
        return {"models": [settings.default_model]}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"LLM server returned HTTP {exc.response.status_code} while checking health.",
                "error_code": "MODEL_ERROR",
            },
        ) from exc
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": "Cannot reach LLM server.", "error_code": "LLM_DOWN"},
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": "Cannot reach LLM server.", "error_code": "LLM_DOWN"},
        ) from exc
