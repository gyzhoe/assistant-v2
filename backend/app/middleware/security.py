"""
Enterprise security middleware for the AI Helpdesk Assistant backend.

Pure ASGI implementations — no BaseHTTPMiddleware overhead.

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
from collections.abc import MutableMapping

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.middleware.asgi_utils import get_client_ip, get_header, send_json_error

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API Token Authentication Middleware
# ---------------------------------------------------------------------------


class APITokenMiddleware:
    """
    Validates authentication on all non-exempt requests.

    Accepts EITHER:
      1. X-Extension-Token header (extension sidebar)
      2. Valid whd_session cookie (management SPA)

    /health, /docs, /openapi.json, and /auth/* are exempt.
    """

    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json"}
    EXEMPT_PREFIXES = ("/auth/", "/manage")

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._token = settings.api_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]

        if path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        # If no token is configured, skip auth (dev mode only)
        if not self._token:
            await self.app(scope, receive, send)
            return

        # Method 1: X-Extension-Token header (extension sidebar)
        provided = get_header(scope, b"x-extension-token")
        if provided and secrets.compare_digest(provided, self._token):
            await self.app(scope, receive, send)
            return

        # Method 2: Valid session cookie (management SPA)
        from app.routers.auth import get_session_id_from_headers, session_store

        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        session_id = get_session_id_from_headers(raw_headers)
        if session_id:
            is_valid = await session_store.validate(session_id)
            if is_valid:
                await self.app(scope, receive, send)
                return

        client_ip = get_client_ip(scope)
        logger.warning("Auth failure on %s from %s", path, client_ip)
        await send_json_error(
            send,
            401,
            {"detail": "Unauthorized. Missing or invalid credentials."},
        )


# ---------------------------------------------------------------------------
# Rate Limiting Middleware
# ---------------------------------------------------------------------------

INGEST_RATE_LIMIT = 5  # max /ingest/upload requests per client IP per minute
FEEDBACK_RATE_LIMIT = 10  # max /feedback requests per client IP per minute


class RateLimitMiddleware:
    """
    Simple in-process rate limiter.
    Limits /generate and /ingest/upload to configurable requests per client IP.

    Uses per-key locks so that requests from different IPs/paths do not
    serialize on a single global lock.  A lightweight background sweep
    (triggered at most once per window) evicts stale entries to bound memory.

    NOTE: This rate limiter uses the client IP from the direct TCP connection.
    Behind a reverse proxy (nginx, Caddy, etc.), all requests appear to come from
    the proxy's IP address, making per-client limiting ineffective — every client
    shares the same bucket and hits the limit together.

    For proxy deployments, choose one of:
      1. Trust X-Forwarded-For: launch uvicorn with ``--proxy-headers`` and
         ``--forwarded-allow-ips`` set to the proxy IP(s) so that
         ``request.client.host`` reflects the real client IP.
      2. Move rate limiting to the proxy layer (nginx ``limit_req_zone``, etc.)
         and rely on the proxy to enforce per-client limits before requests reach
         this application.

    This deployment runs locally (localhost only), so this limitation does not
    apply in the default configuration.
    """

    RATE_LIMITED_PATHS = {"/generate", "/ingest/upload", "/ingest/url", "/feedback"}

    def __init__(self, app: ASGIApp, max_per_minute: int = 20) -> None:
        self.app = app
        self._max = max_per_minute
        self._window = 60.0  # seconds
        # Keyed by "{path}:{ip}" to track per-path, per-IP rate limits
        self._counts: dict[str, list[float]] = defaultdict(list)
        # Per-key locks: only requests sharing the same rate_key contend
        self._key_locks: dict[str, asyncio.Lock] = {}
        # Light lock protecting _key_locks dict and sweep state only
        self._lock = asyncio.Lock()
        self._last_sweep: float = 0.0  # monotonic timestamp of the most-recent cleanup sweep
        self._path_limits: dict[str, int] = {
            "/generate": max_per_minute,
            "/ingest/upload": INGEST_RATE_LIMIT,
            "/ingest/url": INGEST_RATE_LIMIT,
            "/feedback": FEEDBACK_RATE_LIMIT,
        }

    def _evict_stale_entries(self, now: float) -> None:
        """Remove keys whose most-recent request falls outside the current window.

        Must be called while ``self._lock`` is held.  A full sweep is performed
        at most once per window period so that the amortised cost per request is
        negligible even under high load.
        """
        if now - self._last_sweep < self._window:
            return

        stale_keys = [
            k for k, ts in self._counts.items()
            if not ts or now - ts[-1] >= self._window
        ]
        for k in stale_keys:
            del self._counts[k]
            self._key_locks.pop(k, None)

        self._last_sweep = now

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        method: str = scope.get("method", "GET")

        # Only rate-limit mutating methods — safe methods pass through
        if path not in self.RATE_LIMITED_PATHS or method in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        client_ip = get_client_ip(scope)
        rate_key = f"{path}:{client_ip}"
        limit = self._path_limits.get(path, self._max)
        now = time.monotonic()

        # Acquire the per-key lock (create it under the light global lock)
        async with self._lock:
            self._evict_stale_entries(now)
            if rate_key not in self._key_locks:
                self._key_locks[rate_key] = asyncio.Lock()
            key_lock = self._key_locks[rate_key]

        async with key_lock:
            timestamps = self._counts[rate_key]
            # Remove timestamps outside the window
            self._counts[rate_key] = [t for t in timestamps if now - t < self._window]

            if len(self._counts[rate_key]) >= limit:
                logger.warning("Rate limit exceeded for %s on %s", client_ip, path)
                await send_json_error(
                    send,
                    429,
                    {
                        "detail": f"Rate limit exceeded. Max {limit} requests per minute.",
                        "error_code": "RATE_LIMITED",
                    },
                )
                return

            self._counts[rate_key].append(now)

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Request Size Limiting Middleware
# ---------------------------------------------------------------------------


class RequestSizeLimitMiddleware:
    """
    Rejects requests whose body exceeds max_bytes.
    Prevents oversized payloads from being forwarded to the LLM server.
    Default: 64 KB — sufficient for the largest reasonable ticket description.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = 65_536,
        exempt_paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self._max_bytes = max_bytes
        self._exempt_paths = exempt_paths or set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        method: str = scope.get("method", "GET")

        # Check exemptions
        exempt = path in self._exempt_paths or any(
            path.startswith(p + "/") for p in self._exempt_paths
        )
        if exempt:
            await self.app(scope, receive, send)
            return

        # Fast path: check Content-Length header
        content_length_str = get_header(scope, b"content-length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
            except ValueError:
                content_length = 0
            if content_length > self._max_bytes:
                await self._send_too_large(send)
                return
            # Content-Length is within limit; pass through
            await self.app(scope, receive, send)
            return

        # GET/HEAD/OPTIONS typically have no body — skip streaming check
        if method in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        # Streaming path: buffer body chunks, reject if total exceeds limit
        bytes_received = 0
        body_parts: list[bytes] = []
        exceeded = False

        while True:
            message = await receive()
            body_chunk = message.get("body", b"")
            if isinstance(body_chunk, (bytes, bytearray)):
                bytes_received += len(body_chunk)
                body_parts.append(bytes(body_chunk))
            if bytes_received > self._max_bytes:
                exceeded = True
                break
            if not message.get("more_body", False):
                break

        if exceeded:
            await self._send_too_large(send)
            return

        # Replay the consumed body to the inner app
        full_body = b"".join(body_parts)
        body_sent = False

        async def replay_receive() -> dict[str, object]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": full_body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    async def _send_too_large(self, send: Send) -> None:
        await send_json_error(
            send,
            413,
            {
                "detail": f"Request body too large. Max {self._max_bytes} bytes.",
                "error_code": "PAYLOAD_TOO_LARGE",
            },
        )


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware:
    """Adds defensive HTTP security headers to all responses."""

    SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"cache-control", b"no-store"),
        (b"referrer-policy", b"no-referrer"),
    ]

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: MutableMapping[str, object]) -> None:
            if message.get("type") == "http.response.start":
                raw_headers: object = message.get("headers", [])
                headers: list[list[bytes]] = list(raw_headers)  # type: ignore[call-overload]
                # Remove server header if present
                headers = [h for h in headers if h[0].lower() != b"server"]
                # Add security headers
                for name, value in self.SECURITY_HEADERS:
                    headers.append([name, value])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
