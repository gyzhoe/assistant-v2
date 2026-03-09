import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import chromadb
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.constants import KB_COLLECTION, MODEL_DISPLAY_NAMES, TICKET_COLLECTION, LLMModelError
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

    # --- Startup health probes (log-only, not stored) ---
    for label, client_obj, url in [
        ("LLM", llm_client, settings.llm_base_url),
        ("Embed", embed_client, settings.embed_base_url),
    ]:
        try:
            resp = await client_obj.get("/health", timeout=5.0)
            if resp.status_code == 200:
                logger.info("%s server reachable at %s", label, url)
            else:
                logger.warning("%s server not reachable at %s", label, url)
        except Exception:
            logger.warning("%s server not reachable at %s", label, url)

    # Detect which model is actually loaded via /v1/models
    try:
        resp = await llm_client.get("/v1/models", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            models_list = data.get("data", [])
            if models_list:
                model_id: str = models_list[0].get("id", "")
                basename = model_id.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                detected = MODEL_DISPLAY_NAMES.get(
                    model_id,
                    MODEL_DISPLAY_NAMES.get(basename),
                )
                if detected:
                    app.state.current_llm_model = detected
                    logger.info("Detected loaded model: %s", detected)
                else:
                    logger.debug(
                        "Model ID '%s' not in MODEL_DISPLAY_NAMES, "
                        "keeping default '%s'",
                        model_id, settings.default_model,
                    )
    except Exception:
        logger.debug("Could not probe /v1/models, using default model")

    # --- ChromaDB cold-start warm-up ---
    warmup_chromadb(app.state.chroma_client)

    yield

    # --- Cleanup: close httpx clients ---
    await llm_client.aclose()
    await embed_client.aclose()
    await web_client.aclose()
    sync_embed_client.close()


_STATUS_TO_ERROR_CODE: dict[int, str] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    500: ErrorCode.INTERNAL_ERROR,
    502: ErrorCode.MODEL_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


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

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException,
    ) -> JSONResponse:
        """Normalize all HTTPException responses to {message, error_code}."""
        detail = exc.detail

        # Already a dict with error_code — use it directly
        if isinstance(detail, dict) and "error_code" in detail:
            message = str(detail.get("message") or detail.get("detail", ""))
            code = str(detail["error_code"])
            return JSONResponse(
                status_code=exc.status_code,
                content={"message": message, "error_code": code},
            )

        # Plain string detail — map status code to error code
        message = str(detail) if detail else "An error occurred"
        code = _STATUS_TO_ERROR_CODE.get(
            exc.status_code, ErrorCode.INTERNAL_ERROR,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": message, "error_code": code},
        )

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
