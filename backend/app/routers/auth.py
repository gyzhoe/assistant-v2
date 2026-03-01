"""Authentication router for the KB Management SPA.

Provides cookie-based session auth as a secure replacement for
sessionStorage token storage.  The extension sidebar continues to
use the X-Extension-Token header — this module only serves the
management SPA served at /manage.

Endpoints:
    POST /auth/login   — exchange API token for HttpOnly session cookie
    POST /auth/logout  — clear session cookie
    GET  /auth/check   — validate current session
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from http.cookies import SimpleCookie

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings

COOKIE_NAME = "whd_session"

# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------


@dataclass
class SessionData:
    created_at: float
    expires_at: float


@dataclass
class SessionStore:
    """Thread-safe in-memory session store with expiry sweep."""

    _sessions: dict[str, SessionData] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def create(self, max_age: int) -> str:
        """Create a new session and return its ID.  Sweeps expired entries."""
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        async with self._lock:
            self._sweep(now)
            self._sessions[session_id] = SessionData(
                created_at=now,
                expires_at=now + max_age,
            )
        return session_id

    async def validate(self, session_id: str) -> bool:
        """Return True if the session exists and has not expired."""
        now = time.time()
        async with self._lock:
            data = self._sessions.get(session_id)
            if data is None:
                return False
            if now >= data.expires_at:
                del self._sessions[session_id]
                return False
            return True

    async def remove(self, session_id: str) -> None:
        """Delete a session by ID (no-op if missing)."""
        async with self._lock:
            self._sessions.pop(session_id, None)

    def _sweep(self, now: float) -> None:
        """Remove all expired sessions.  Must be called under lock."""
        expired = [
            sid for sid, data in self._sessions.items() if now >= data.expires_at
        ]
        for sid in expired:
            del self._sessions[sid]


# Module-level singleton so the middleware can import it.
session_store = SessionStore()


def get_session_id_from_headers(headers: list[tuple[bytes, bytes]]) -> str | None:
    """Parse the whd_session cookie from raw ASGI / Starlette headers."""
    for key, value in headers:
        if key == b"cookie":
            cookie: SimpleCookie = SimpleCookie()
            cookie.load(value.decode("latin-1"))
            morsel = cookie.get(COOKIE_NAME)
            if morsel is not None:
                return str(morsel.value)
    return None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["auth"])


@router.post("/login")
async def login(request: Request) -> JSONResponse:
    """Exchange an API token for an HttpOnly session cookie."""
    body = await request.json()
    provided_token: str = body.get("token", "")

    # If no API token is configured (dev mode), login always succeeds.
    if settings.api_token:
        if not provided_token or not secrets.compare_digest(
            provided_token, settings.api_token
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API token."},
            )

    max_age = settings.session_max_age
    session_id = await session_store.create(max_age)

    response = JSONResponse(content={"authenticated": True})
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=False,  # localhost — no TLS
        path="/",
        max_age=max_age,
    )
    return response


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Clear the session cookie and remove the session from the store."""
    session_id = request.cookies.get(COOKIE_NAME, "")
    if session_id:
        await session_store.remove(session_id)

    response = JSONResponse(content={"authenticated": False})
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    return response


@router.get("/check")
async def check_session(request: Request) -> JSONResponse:
    """Return whether the current session cookie is valid."""
    session_id = request.cookies.get(COOKIE_NAME, "")
    if not session_id:
        return JSONResponse(content={"authenticated": False})

    is_valid = await session_store.validate(session_id)
    return JSONResponse(content={"authenticated": is_valid})
