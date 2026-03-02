import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import chromadb
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.logging_config import setup_logging
from app.middleware.csrf import CSRFMiddleware
from app.middleware.security import (
    APITokenMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.routers import auth, feedback, generate, health, ingest, kb, models

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize ChromaDB client and verify Ollama on startup."""
    logger.info("Starting AI Helpdesk Assistant backend v%s", settings.version)

    app.state.chroma_client = chromadb.PersistentClient(path=settings.chroma_path)
    logger.info("ChromaDB initialized at %s", settings.chroma_path)

    app.state.ollama_reachable = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            app.state.ollama_reachable = resp.status_code == 200
    except Exception:
        app.state.ollama_reachable = False

    if app.state.ollama_reachable:
        logger.info("Ollama reachable at %s", settings.ollama_base_url)
    else:
        logger.warning("Ollama not reachable at %s", settings.ollama_base_url)

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Helpdesk Assistant Backend",
        version=settings.version,
        lifespan=lifespan,
    )

    # Middleware is applied in reverse order (last added = outermost wrapper).
    # Execution order for a request:
    #   SecurityHeaders → CORS → SizeLimit → RateLimit → APIToken → CSRF → router
    # So we add them in reverse: CSRF first (innermost), SecurityHeaders last (outermost).

    # CSRF protection — innermost, runs after auth verifies the session
    app.add_middleware(CSRFMiddleware)

    app.add_middleware(APITokenMiddleware)

    app.add_middleware(
        RateLimitMiddleware,
        max_per_minute=settings.rate_limit_per_minute,
    )

    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=settings.max_request_bytes,
        exempt_paths={"/ingest/upload", "/ingest/url", "/kb/articles"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Extension-Token", "X-CSRF-Token"],
    )

    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(health.router)
    app.include_router(generate.router)
    app.include_router(models.router)
    app.include_router(ingest.router)
    app.include_router(kb.router)
    app.include_router(feedback.router)

    # Static file serving for KB management SPA — must come AFTER API routes
    # so /kb/* API endpoints take priority over static file catch-all.
    #
    # NOTE: The /manage static mount serves the KB management SPA without
    # authentication. This is intentional for the default local-only deployment
    # (localhost:8765), where network access is already restricted to the local
    # machine. For network-exposed deployments (e.g., serving from a shared
    # server), add authentication middleware or serve /manage behind an
    # authenticated reverse proxy before exposing it to untrusted clients.
    _manage_dir = Path(__file__).resolve().parent.parent / "static" / "manage"
    if _manage_dir.is_dir():
        app.mount(
            "/manage",
            StaticFiles(directory=str(_manage_dir), html=True),
            name="management",
        )

    return app


app = create_app()
