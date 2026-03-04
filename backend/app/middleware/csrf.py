"""CSRF protection middleware — double-submit cookie pattern.

For the management SPA (cookie-authenticated):
1. On login, a separate non-HttpOnly cookie ``whd_csrf`` is set containing
   a random token.  The SPA reads this cookie via JavaScript and sends it
   back in the ``X-CSRF-Token`` header on every mutating request.
2. This middleware validates that the header value matches the cookie value
   on POST/PUT/PATCH/DELETE requests to protected paths.

Extension requests (X-Extension-Token header) are exempt because they use
a shared secret, not cookies, so CSRF does not apply.

GET/HEAD/OPTIONS are always exempt (safe methods).
"""

from __future__ import annotations

import logging
import secrets
from http.cookies import SimpleCookie

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.middleware.asgi_utils import get_header, send_json_error

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "whd_csrf"
CSRF_HEADER_NAME = b"x-csrf-token"

# Paths that require CSRF validation on mutating methods
CSRF_PROTECTED_PREFIXES = ("/kb/", "/ingest/", "/feedback", "/generate", "/models")

# Paths exempt from CSRF (auth endpoints handle their own security)
CSRF_EXEMPT_PREFIXES = ("/auth/",)

# Safe HTTP methods that never need CSRF protection
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _get_cookie(scope: Scope, cookie_name: str) -> str:
    """Extract a cookie value from ASGI scope headers."""
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for key, value in headers:
        if key == b"cookie":
            cookie: SimpleCookie = SimpleCookie()
            cookie.load(value.decode("latin-1"))
            morsel = cookie.get(cookie_name)
            if morsel is not None:
                return str(morsel.value)
    return ""


class CSRFMiddleware:
    """Double-submit cookie CSRF protection for the management SPA.

    Validates X-CSRF-Token header against whd_csrf cookie on
    POST/PUT/PATCH/DELETE to protected paths.

    Extension requests (identified by X-Extension-Token header) are
    exempt — they authenticate via a shared secret, not cookies.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._token = settings.api_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # If no API token is configured (dev mode), skip CSRF — no sessions exist
        if not self._token:
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        method: str = scope.get("method", "GET")

        # Safe methods never need CSRF
        if method in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        # Auth endpoints are exempt
        if any(path.startswith(p) for p in CSRF_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Check if path needs CSRF protection
        needs_csrf = any(
            path.startswith(p) or path == p.rstrip("/")
            for p in CSRF_PROTECTED_PREFIXES
        )
        if not needs_csrf:
            await self.app(scope, receive, send)
            return

        # Extension requests are exempt (they use header-based auth, not cookies)
        extension_token = get_header(scope, b"x-extension-token")
        if extension_token:
            await self.app(scope, receive, send)
            return

        # Validate CSRF: cookie must exist AND header must match
        csrf_cookie = _get_cookie(scope, CSRF_COOKIE_NAME)
        csrf_header = get_header(scope, CSRF_HEADER_NAME)

        if not csrf_cookie or not csrf_header:
            logger.warning(
                "CSRF validation failed on %s %s — missing token",
                method, path,
            )
            await send_json_error(send, 403, {"detail": "CSRF token missing."})
            return

        if not secrets.compare_digest(csrf_cookie, csrf_header):
            logger.warning(
                "CSRF validation failed on %s %s — token mismatch",
                method, path,
            )
            await send_json_error(send, 403, {"detail": "CSRF token mismatch."})
            return

        await self.app(scope, receive, send)


def generate_csrf_token() -> str:
    """Generate a new CSRF token (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)
