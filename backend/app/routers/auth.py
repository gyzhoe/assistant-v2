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

import secrets
from http.cookies import SimpleCookie

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.middleware.csrf import CSRF_COOKIE_NAME, generate_csrf_token
from app.services.audit import audit_log
from app.services.session_store import (
    MemorySessionStore,
    SQLiteSessionStore,
    create_session_store,
)

COOKIE_NAME = "whd_session"

# Module-level singleton so the middleware can import it.
session_store: MemorySessionStore | SQLiteSessionStore = create_session_store()


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

    client_ip = request.client.host if request.client else ""

    # If no API token is configured (dev mode), login always succeeds.
    if settings.api_token:
        if not provided_token or not secrets.compare_digest(
            provided_token, settings.api_token
        ):
            audit_log("login", client_ip=client_ip, outcome="failure")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API token."},
            )

    max_age = settings.session_max_age
    session_id = await session_store.create(max_age, client_ip=client_ip)
    audit_log("login", client_ip=client_ip, session_id=session_id)

    secure = settings.session_cookie_secure

    response = JSONResponse(content={"authenticated": True})
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
        max_age=max_age,
    )
    # Set CSRF cookie — non-HttpOnly so the SPA JavaScript can read it
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=generate_csrf_token(),
        httponly=False,
        samesite="strict",
        secure=secure,
        path="/",
        max_age=max_age,
    )
    return response


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Clear the session cookie and remove the session from the store."""
    client_ip = request.client.host if request.client else ""
    session_id = request.cookies.get(COOKIE_NAME, "")
    if session_id:
        await session_store.remove(session_id)
    audit_log("logout", client_ip=client_ip, session_id=session_id)

    secure = settings.session_cookie_secure

    response = JSONResponse(content={"authenticated": False})
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        httponly=False,
        samesite="strict",
        secure=secure,
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
