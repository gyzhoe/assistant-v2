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
