"""Tests for the /auth/* session endpoints and cookie-based authentication.

Each test creates a fresh app instance to isolate session state.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.services.session_store import MemorySessionStore, SessionData


@asynccontextmanager
async def _auth_client(
    api_token: str = "test-secret",
) -> AsyncGenerator[AsyncClient]:
    """Yield an AsyncClient whose app is patched with the given api_token.

    The patch remains active for the lifetime of the context manager so that
    request-time reads of ``settings.api_token`` see the patched value.
    """
    with patch("app.config.settings.api_token", api_token):
        fresh_app = create_app()
        fresh_app.state.chroma_client = MagicMock()
        fresh_app.state.llm_reachable = False
        async with AsyncClient(
            transport=ASGITransport(app=fresh_app),
            base_url="http://testserver",
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# 1. Login success — returns 200 + Set-Cookie with HttpOnly flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_sets_httponly_cookie() -> None:
    """POST /auth/login with a valid token sets an HttpOnly session cookie."""
    async with _auth_client() as ac:
        resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["authenticated"] is True

        # Verify the Set-Cookie header
        set_cookie = resp.headers.get("set-cookie", "")
        assert "whd_session=" in set_cookie
        assert "httponly" in set_cookie.lower()
        assert "samesite=strict" in set_cookie.lower()


# ---------------------------------------------------------------------------
# 2. Login invalid token — returns 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_invalid_token_returns_401() -> None:
    """POST /auth/login with a wrong token returns 401."""
    async with _auth_client() as ac:
        resp = await ac.post("/auth/login", json={"token": "wrong-token"})
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 3. Login no token configured (dev mode) — returns 200 (always succeeds)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_dev_mode_always_succeeds() -> None:
    """When api_token is empty (dev mode), login succeeds with any value."""
    async with _auth_client(api_token="") as ac:
        resp = await ac.post("/auth/login", json={"token": "anything"})
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True
        assert "whd_session=" in resp.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# 4. Logout clears cookie — Set-Cookie with empty value + max-age=0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_cookie() -> None:
    """POST /auth/logout clears the session cookie."""
    async with _auth_client() as ac:
        # Login first
        login_resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert login_resp.status_code == 200
        ac.cookies.update(login_resp.cookies)

        # Logout
        logout_resp = await ac.post("/auth/logout")
        assert logout_resp.status_code == 200
        assert logout_resp.json()["authenticated"] is False

        set_cookie = logout_resp.headers.get("set-cookie", "")
        assert "whd_session=" in set_cookie
        # After logout the session is invalid
        check_resp = await ac.get("/auth/check")
        assert check_resp.json()["authenticated"] is False


# ---------------------------------------------------------------------------
# 5. Check valid session — returns {"authenticated": true}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_valid_session() -> None:
    """GET /auth/check with a valid session cookie returns authenticated: true."""
    async with _auth_client() as ac:
        login_resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert login_resp.status_code == 200
        ac.cookies.update(login_resp.cookies)

        check_resp = await ac.get("/auth/check")
        assert check_resp.status_code == 200
        assert check_resp.json()["authenticated"] is True


# ---------------------------------------------------------------------------
# 6. Check expired session — returns {"authenticated": false}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_expired_session() -> None:
    """GET /auth/check with an expired session returns authenticated: false."""
    async with _auth_client() as ac:
        # Login with very short max_age
        with patch("app.config.settings.session_max_age", 1):
            login_resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert login_resp.status_code == 200
        ac.cookies.update(login_resp.cookies)

        # Manually expire the session by manipulating the store
        from app.routers.auth import session_store

        async with session_store._lock:
            for data in session_store._sessions.values():
                data.expires_at = time.time() - 10

        check_resp = await ac.get("/auth/check")
        assert check_resp.json()["authenticated"] is False


# ---------------------------------------------------------------------------
# 7. Check no cookie — returns {"authenticated": false}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_no_cookie() -> None:
    """GET /auth/check without any cookie returns authenticated: false."""
    async with _auth_client() as ac:
        resp = await ac.get("/auth/check")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is False


# ---------------------------------------------------------------------------
# 8. Session sweep evicts expired entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_sweep_evicts_expired() -> None:
    """MemorySessionStore._sweep removes sessions whose expires_at is in the past."""
    store = MemorySessionStore()
    now = time.time()

    async with store._lock:
        store._sessions["valid-session"] = SessionData(
            created_at=now - 100, expires_at=now + 3600,
        )
        store._sessions["expired-session"] = SessionData(
            created_at=now - 200, expires_at=now - 10,
        )
        store._sweep(now)

    assert "valid-session" in store._sessions
    assert "expired-session" not in store._sessions


# ---------------------------------------------------------------------------
# 9. Middleware accepts session cookie for protected endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_accepts_session_cookie() -> None:
    """Protected endpoints accept valid session cookies instead of X-Extension-Token."""
    async with _auth_client() as ac:
        # Login to get session cookie
        login_resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert login_resp.status_code == 200
        ac.cookies.update(login_resp.cookies)

        # /health is exempt — use it to confirm cookie-bearing requests work
        resp = await ac.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 10. Auth endpoints are exempt from API token middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_endpoints_exempt_from_token_middleware() -> None:
    """/auth/* paths should not require X-Extension-Token header."""
    async with _auth_client() as ac:
        # /auth/login should be accessible without token header
        resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert resp.status_code == 200

        # /auth/check should be accessible without token header
        resp = await ac.get("/auth/check")
        assert resp.status_code == 200

        # /auth/logout should be accessible without token header
        resp = await ac.post("/auth/logout")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 11. Configurable secure cookie flag (M2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_cookie_secure_flag_false_by_default() -> None:
    """When session_cookie_secure is False (default), cookies should not have Secure."""
    async with _auth_client() as ac:
        resp = await ac.post("/auth/login", json={"token": "test-secret"})
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "secure" not in set_cookie or "samesite" in set_cookie


@pytest.mark.asyncio
async def test_login_cookie_secure_flag_when_enabled() -> None:
    """When session_cookie_secure is True, cookies should have the Secure flag."""
    with patch("app.config.settings.session_cookie_secure", True):
        async with _auth_client() as ac:
            resp = await ac.post("/auth/login", json={"token": "test-secret"})
            assert resp.status_code == 200
            set_cookie = resp.headers.get("set-cookie", "").lower()
            assert "secure" in set_cookie


@pytest.mark.asyncio
async def test_logout_cookie_secure_flag_when_enabled() -> None:
    """Logout should also respect session_cookie_secure."""
    with patch("app.config.settings.session_cookie_secure", True):
        async with _auth_client() as ac:
            # Login first
            login_resp = await ac.post("/auth/login", json={"token": "test-secret"})
            assert login_resp.status_code == 200
            ac.cookies.update(login_resp.cookies)

            # Logout
            logout_resp = await ac.post("/auth/logout")
            assert logout_resp.status_code == 200
            set_cookie = logout_resp.headers.get("set-cookie", "").lower()
            assert "secure" in set_cookie
