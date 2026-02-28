"""
Enterprise security middleware for the AI Helpdesk Assistant backend.

Provides:
- API token authentication (shared secret between extension and backend)
- Request size limiting
- Rate limiting per client
- Security headers
"""

import asyncio
import logging
import secrets
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API Token Authentication Middleware
# ---------------------------------------------------------------------------

class APITokenMiddleware(BaseHTTPMiddleware):
    """
    Validates the X-Extension-Token header on all non-health requests.

    The extension sends a shared secret configured in both:
      - Backend: API_TOKEN env var (required in production)
      - Extension: stored in chrome.storage.local (never synced)

    /health is exempt so operators can monitor without the token.
    """

    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._token = settings.api_token

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # If no token is configured, skip auth (dev mode only)
        if not self._token:
            return await call_next(request)

        provided = request.headers.get("X-Extension-Token", "")
        if not provided or not secrets.compare_digest(provided, self._token):
            logger.warning("Auth failure on %s from %s", request.url.path, request.client.host if request.client else "unknown")
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized. Missing or invalid X-Extension-Token header."},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Rate Limiting Middleware
# ---------------------------------------------------------------------------

INGEST_RATE_LIMIT = 5  # max /ingest/upload requests per client IP per minute


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-process rate limiter.
    Limits /generate and /ingest/upload to configurable requests per client IP.

    Memory management: a periodic sweep (at most once per window) evicts entries
    for IPs whose most-recent request is older than the window.  This prevents
    unbounded growth of ``_counts`` when the server receives traffic from many
    distinct source IPs over time.
    """

    RATE_LIMITED_PATHS = {"/generate", "/ingest/upload", "/ingest/url"}

    def __init__(self, app: ASGIApp, max_per_minute: int = 20) -> None:
        super().__init__(app)
        self._max = max_per_minute
        self._window = 60.0  # seconds
        # Keyed by "{path}:{ip}" to track per-path, per-IP rate limits
        self._counts: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._last_sweep: float = 0.0  # monotonic timestamp of the most-recent cleanup sweep
        self._path_limits: dict[str, int] = {
            "/generate": max_per_minute,
            "/ingest/upload": INGEST_RATE_LIMIT,
            "/ingest/url": INGEST_RATE_LIMIT,
        }

    def _evict_stale_entries(self, now: float) -> None:
        """Remove IPs whose most-recent request falls outside the current window.

        Must be called while ``self._lock`` is held.  A full sweep is performed
        at most once per window period so that the amortised cost per request is
        negligible even under high load.
        """
        if now - self._last_sweep < self._window:
            return

        stale_ips = [ip for ip, ts in self._counts.items() if not ts or now - ts[-1] >= self._window]
        for ip in stale_ips:
            del self._counts[ip]

        self._last_sweep = now

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path not in self.RATE_LIMITED_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        rate_key = f"{request.url.path}:{client_ip}"
        limit = self._path_limits.get(request.url.path, self._max)
        now = time.monotonic()

        async with self._lock:
            # Periodic cleanup: evict stale IP entries to bound memory usage.
            self._evict_stale_entries(now)

            timestamps = self._counts[rate_key]
            # Remove timestamps outside the window
            self._counts[rate_key] = [t for t in timestamps if now - t < self._window]

            if len(self._counts[rate_key]) >= limit:
                logger.warning("Rate limit exceeded for %s on %s", client_ip, request.url.path)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Rate limit exceeded. Max {limit} requests per minute.",
                        "error_code": "RATE_LIMITED",
                    },
                )

            self._counts[rate_key].append(now)

        return await call_next(request)


# ---------------------------------------------------------------------------
# Request Size Limiting Middleware
# ---------------------------------------------------------------------------

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Rejects requests whose body exceeds max_bytes.
    Prevents oversized payloads from being forwarded to Ollama.
    Default: 64 KB — sufficient for the largest reasonable ticket description.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = 65_536,
        exempt_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes
        self._exempt_paths = exempt_paths or set()

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        exempt = request.url.path in self._exempt_paths or any(
            request.url.path.startswith(p + "/") for p in self._exempt_paths
        )
        if exempt:
            return await call_next(request)
        content_length = request.headers.get("content-length")
        if content_length:
            if int(content_length) > self._max_bytes:
                return self._too_large()
        elif request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > self._max_bytes:
                return self._too_large()
        return await call_next(request)

    def _too_large(self) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={
                "detail": f"Request body too large. Max {self._max_bytes} bytes.",
                "error_code": "PAYLOAD_TOO_LARGE",
            },
        )


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds defensive HTTP security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Remove server version banner
        if "server" in response.headers:
            del response.headers["server"]
        return response
