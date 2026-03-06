"""Tests for CSRF protection middleware.

Verifies:
- CSRF cookie is set on login, cleared on logout
- POST/PUT/PATCH/DELETE to protected paths require matching CSRF token
- GET requests are always exempt
- Extension requests (X-Extension-Token) bypass CSRF
- Auth endpoints are exempt
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.middleware.csrf import CSRF_COOKIE_NAME
from tests.helpers import setup_app_state


@asynccontextmanager
async def _csrf_client(
    api_token: str = "test-secret",
) -> AsyncGenerator[AsyncClient]:
    """Yield an AsyncClient with CSRF middleware active."""
    with patch("app.config.settings.api_token", api_token):
        fresh_app = create_app()
        fresh_app.state.chroma_client = MagicMock()
        fresh_app.state.llm_reachable = False
        setup_app_state(fresh_app)
        async with AsyncClient(
            transport=ASGITransport(app=fresh_app),
            base_url="http://testserver",
        ) as ac:
            yield ac


async def _login_and_get_csrf(
    ac: AsyncClient, token: str = "test-secret",
) -> tuple[str, str]:
    """Login and return (session_cookie_header, csrf_token)."""
    resp = await ac.post("/auth/login", json={"token": token})
    assert resp.status_code == 200
    ac.cookies.update(resp.cookies)

    # Extract CSRF token from cookie
    csrf_token = resp.cookies.get(CSRF_COOKIE_NAME, "")
    assert csrf_token, "CSRF cookie should be set on login"
    return csrf_token, csrf_token


# ---------------------------------------------------------------------------
# 1. Login sets CSRF cookie
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_sets_csrf_cookie() -> None:
    """POST /auth/login should set a non-HttpOnly CSRF cookie."""
    async with _csrf_client() as ac:
        resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert resp.status_code == 200

        set_cookies = resp.headers.get_list("set-cookie")
        csrf_cookies = [c for c in set_cookies if CSRF_COOKIE_NAME in c]
        assert len(csrf_cookies) == 1

        csrf_cookie = csrf_cookies[0]
        # CSRF cookie must NOT be httponly (SPA needs to read it)
        assert "httponly" not in csrf_cookie.lower() or (
            "httponly" in csrf_cookie.lower()
            and csrf_cookie.lower().index(CSRF_COOKIE_NAME)
            < csrf_cookie.lower().index("httponly")
            and "whd_session" in csrf_cookie  # wrong cookie
        )


# ---------------------------------------------------------------------------
# 2. Logout clears CSRF cookie
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_csrf_cookie() -> None:
    """POST /auth/logout should clear the CSRF cookie."""
    async with _csrf_client() as ac:
        await _login_and_get_csrf(ac)
        resp = await ac.post("/auth/logout")
        assert resp.status_code == 200

        set_cookies = resp.headers.get_list("set-cookie")
        csrf_deletions = [
            c for c in set_cookies
            if CSRF_COOKIE_NAME in c and ('max-age=0' in c.lower() or '""' in c)
        ]
        assert len(csrf_deletions) >= 1


# ---------------------------------------------------------------------------
# 3. POST to protected path without CSRF token → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_to_kb_without_csrf_token_is_rejected() -> None:
    """POST to /kb/articles without CSRF token should return 403."""
    async with _csrf_client() as ac:
        csrf_token, _ = await _login_and_get_csrf(ac)

        # Remove CSRF cookie and header — simulate missing token
        ac.cookies.delete(CSRF_COOKIE_NAME)

        resp = await ac.post(
            "/kb/articles",
            json={"title": "Test", "content": "Test content"},
        )
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4. POST to protected path with valid CSRF token → passes through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_to_feedback_with_valid_csrf_passes() -> None:
    """POST to /feedback with valid CSRF token should reach the router."""
    async with _csrf_client() as ac:
        csrf_token, _ = await _login_and_get_csrf(ac)

        # Mock the embed service on app.state (singleton pattern)
        ac._transport.app.state.embed_service.embed = AsyncMock(  # type: ignore[union-attr]
            return_value=[0.1] * 384,
        )

        # Mock ChromaDB collection
        mock_col = MagicMock()
        mock_col.add = MagicMock()
        ac._transport.app.state.chroma_client.get_or_create_collection = (  # type: ignore[union-attr]
            MagicMock(return_value=mock_col)
        )

        resp = await ac.post(
            "/feedback",
            json={
                "ticket_subject": "VPN issue",
                "ticket_description": "Cannot connect",
                "reply": "Try reconnecting",
                "rating": "good",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        # Should reach the router (200) not be blocked by CSRF (403)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. POST with mismatched CSRF token → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_with_mismatched_csrf_token_is_rejected() -> None:
    """POST with wrong CSRF header value should return 403."""
    async with _csrf_client() as ac:
        await _login_and_get_csrf(ac)

        resp = await ac.post(
            "/kb/articles",
            json={"title": "Test", "content": "Test"},
            headers={"X-CSRF-Token": "wrong-token-value"},
        )
        assert resp.status_code == 403
        assert "mismatch" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 6. GET requests are always exempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_requests_bypass_csrf() -> None:
    """GET /kb/articles should not require CSRF token."""
    async with _csrf_client() as ac:
        await _login_and_get_csrf(ac)

        # GET to protected path — should work without CSRF header
        resp = await ac.get("/kb/articles")
        # May be 200 or 500 (no real ChromaDB), but NOT 403
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# 7. Extension requests (X-Extension-Token) bypass CSRF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extension_token_bypasses_csrf() -> None:
    """Requests with X-Extension-Token should bypass CSRF check."""
    async with _csrf_client() as ac:
        # Don't login — use extension token directly
        ac._transport.app.state.embed_service.embed = AsyncMock(  # type: ignore[union-attr]
            return_value=[0.1] * 384,
        )

        mock_col = MagicMock()
        mock_col.add = MagicMock()
        ac._transport.app.state.chroma_client.get_or_create_collection = (  # type: ignore[union-attr]
            MagicMock(return_value=mock_col)
        )

        resp = await ac.post(
            "/feedback",
            json={
                "ticket_subject": "VPN issue",
                "ticket_description": "Cannot connect",
                "reply": "Try reconnecting",
                "rating": "good",
            },
            headers={"X-Extension-Token": "test-secret"},
        )
        # Should pass through — NOT 403
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# 8. DELETE to protected path needs CSRF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_without_csrf_is_rejected() -> None:
    """DELETE to /feedback/{id} without CSRF should return 403."""
    async with _csrf_client() as ac:
        csrf_token, _ = await _login_and_get_csrf(ac)

        # Remove CSRF cookie
        ac.cookies.delete(CSRF_COOKIE_NAME)

        resp = await ac.delete("/feedback/some-id")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 9. Auth endpoints exempt from CSRF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_endpoints_exempt_from_csrf() -> None:
    """POST /auth/login and /auth/logout should not need CSRF token."""
    async with _csrf_client() as ac:
        # Login — no CSRF needed
        resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert resp.status_code == 200

        # Logout — no CSRF needed
        ac.cookies.update(resp.cookies)
        resp = await ac.post("/auth/logout")
        assert resp.status_code == 200
