import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import chromadb
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.constants import LLMModelError
from app.logging_config import setup_logging
from app.middleware.csrf import CSRFMiddleware
from app.middleware.security import (
    APITokenMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    UnhandledExceptionMiddleware,
)
from app.models.response_models import ErrorCode, ErrorResponse
from app.routers import auth, feedback, generate, health, ingest, kb, models
from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService
from app.services.microsoft_docs import MicrosoftDocsService
from app.services.model_download_service import ModelDownloadService
from app.services.rag_service import RAGService

setup_logging()
logger = logging.getLogger(__name__)


def warmup_chromadb(chroma_client: "chromadb.api.ClientAPI") -> None:
    """Warm up ChromaDB collections to avoid cold-start latency on first query."""
    from app.constants import KB_COLLECTION, TICKET_COLLECTION

    for col_name in (KB_COLLECTION, TICKET_COLLECTION):
        try:
            col = chroma_client.get_collection(col_name)
            count = col.count()
            logger.info("ChromaDB warm-up: %s has %d documents", col_name, count)
        except Exception:
            logger.debug(
                "ChromaDB warm-up: %s not found (will be created on first ingest)",
                col_name,
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize shared clients and services on startup, close on shutdown."""
    logger.info("Starting AI Helpdesk Assistant backend v%s", settings.version)

    # --- Shared httpx clients (connection pooling) ---
    llm_client = httpx.AsyncClient(
        base_url=settings.llm_base_url,
        timeout=120.0,
    )
    embed_client = httpx.AsyncClient(
        base_url=settings.embed_base_url,
        timeout=30.0,
    )
    web_client = httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=True,
        max_redirects=3,
    )
    # Sync client for ingestion pipelines (run in to_thread)
    sync_embed_client = httpx.Client(
        base_url=settings.embed_base_url,
        timeout=30.0,
    )

    # --- ChromaDB ---
    app.state.chroma_client = chromadb.PersistentClient(path=settings.chroma_path)
    logger.info("ChromaDB initialized at %s", settings.chroma_path)

    # --- Singleton services ---
    app.state.llm_service = LLMService(client=llm_client)
    app.state.embed_service = EmbedService(client=embed_client)
    app.state.sync_embed_service = EmbedService(client=sync_embed_client)
    app.state.ms_docs_service = MicrosoftDocsService(client=web_client)
    app.state.rag_service = RAGService(
        chroma_client=app.state.chroma_client,
        embed_svc=app.state.embed_service,
    )

    # --- Current LLM model tracking ---
    app.state.current_llm_model = settings.default_model

    # --- Model download service ---
    app.state.model_download_service = ModelDownloadService()

    # --- LLM health probe ---
    app.state.llm_reachable = False
    try:
        resp = await llm_client.get("/health", timeout=5.0)
        app.state.llm_reachable = resp.status_code == 200
    except Exception:
        app.state.llm_reachable = False

    # --- Embed health probe ---
    app.state.embed_reachable = False
    try:
        resp = await embed_client.get("/health", timeout=5.0)
        app.state.embed_reachable = resp.status_code == 200
    except Exception:
        app.state.embed_reachable = False

    if app.state.llm_reachable:
        logger.info("LLM server reachable at %s", settings.llm_base_url)
    else:
        logger.warning("LLM server not reachable at %s", settings.llm_base_url)

    if app.state.embed_reachable:
        logger.info("Embed server reachable at %s", settings.embed_base_url)
    else:
        logger.warning("Embed server not reachable at %s", settings.embed_base_url)

    # --- ChromaDB cold-start warm-up ---
    warmup_chromadb(app.state.chroma_client)

    yield

    # --- Cleanup: close httpx clients ---
    await llm_client.aclose()
    await embed_client.aclose()
    await web_client.aclose()
    sync_embed_client.close()


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

    # Catch-all for unhandled exceptions — outermost ASGI middleware
    # so it catches anything that slips past all other layers.
    app.add_middleware(UnhandledExceptionMiddleware)

    # --- Global exception handlers ---

    @app.exception_handler(ConnectionError)
    async def connection_error_handler(
        request: Request, exc: ConnectionError,
    ) -> JSONResponse:
        logger.error("LLM connection error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                message=str(exc),
                error_code=ErrorCode.LLM_DOWN,
            ).model_dump(),
        )

    @app.exception_handler(LLMModelError)
    async def llm_model_error_handler(
        request: Request, exc: LLMModelError,
    ) -> JSONResponse:
        logger.error("LLM model error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                message=str(exc),
                error_code=ErrorCode.MODEL_ERROR,
            ).model_dump(),
        )

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
