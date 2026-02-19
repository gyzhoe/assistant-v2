from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import chromadb
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware.security import (
    APITokenMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.routers import generate, health, ingest, models


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize ChromaDB client and verify Ollama on startup."""
    app.state.chroma_client = chromadb.PersistentClient(path=settings.chroma_path)
    app.state.ollama_reachable = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            app.state.ollama_reachable = resp.status_code == 200
    except Exception:
        app.state.ollama_reachable = False
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Helpdesk Assistant Backend",
        version=settings.version,
        lifespan=lifespan,
    )

    # Middleware is applied in reverse order (last added = outermost wrapper)
    # Execution order for a request: SecurityHeaders → CORS → SizeLimit → RateLimit → APIToken → router

    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Extension-Token"],
    )

    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=settings.max_request_bytes,
    )

    app.add_middleware(
        RateLimitMiddleware,
        max_per_minute=settings.rate_limit_per_minute,
    )

    app.add_middleware(APITokenMiddleware)

    app.include_router(health.router)
    app.include_router(generate.router)
    app.include_router(models.router)
    app.include_router(ingest.router)

    return app


app = create_app()
