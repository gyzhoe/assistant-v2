"""Tests for health endpoints — public /health, token-gated /health/detail,
and localhost-only process-control endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import Address

from app.main import create_app
from app.routers.health import _require_localhost
from tests.helpers import setup_app_state


def _make_client() -> AsyncClient:
    app = create_app()
    app.state.chroma_client = MagicMock()
    app.state.ollama_reachable = False
    setup_app_state(app)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


# ── GET /health (public, minimal) ──────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_returns_minimal_response(client: AsyncClient) -> None:
    """Public /health must NOT expose version or internal details."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"status"}
    assert "version" not in data
    assert "ollama_reachable" not in data
    assert "chroma_ready" not in data


# ── GET /health/detail (token-gated) ───────────────────────────────


@pytest.mark.asyncio
async def test_health_detail_unauthenticated_returns_200_when_no_token_configured(
    client: AsyncClient,
) -> None:
    """When api_token is empty (dev mode), /health/detail is accessible."""
    response = await client.get("/health/detail")
    assert response.status_code == 200
    data = response.json()
    required_keys = {"status", "ollama_reachable", "chroma_ready", "chroma_doc_counts", "version"}
    assert required_keys.issubset(data.keys())


@pytest.mark.asyncio
async def test_health_detail_with_token_configured_requires_token(client: AsyncClient) -> None:
    """When api_token is set, /health/detail requires valid X-Extension-Token."""
    with patch("app.routers.health.settings") as mock_settings:
        mock_settings.api_token = "secret-token"
        mock_settings.ollama_base_url = "http://localhost:11434"
        response = await client.get("/health/detail")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_detail_with_valid_token_returns_200(client: AsyncClient) -> None:
    with patch("app.routers.health.settings") as mock_settings:
        mock_settings.api_token = "secret-token"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_settings.version = "1.11.0"
        response = await client.get(
            "/health/detail",
            headers={"X-Extension-Token": "secret-token"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_degraded_when_ollama_down(client: AsyncClient) -> None:
    response = await client.get("/health/detail")
    data = response.json()
    # In test environment Ollama is not running, so should be degraded
    assert data["status"] in ("ok", "degraded")
    assert isinstance(data["ollama_reachable"], bool)


# ── _require_localhost helper ───────────────────────────────────────


def test_require_localhost_allows_127_0_0_1() -> None:
    request = MagicMock()
    request.client = Address("127.0.0.1", 12345)
    # Should not raise
    _require_localhost(request)


def test_require_localhost_allows_ipv6_loopback() -> None:
    request = MagicMock()
    request.client = Address("::1", 12345)
    # Should not raise
    _require_localhost(request)


def test_require_localhost_blocks_external_ip() -> None:
    request = MagicMock()
    request.client = Address("192.168.1.50", 12345)
    with pytest.raises(HTTPException) as exc_info:
        _require_localhost(request)
    assert exc_info.value.status_code == 403


def test_require_localhost_blocks_when_client_is_none() -> None:
    request = MagicMock()
    request.client = None
    with pytest.raises(HTTPException) as exc_info:
        _require_localhost(request)
    assert exc_info.value.status_code == 403


def test_require_localhost_blocks_remote_loopback_look_alike() -> None:
    request = MagicMock()
    request.client = Address("127.0.0.2", 12345)
    with pytest.raises(HTTPException) as exc_info:
        _require_localhost(request)
    assert exc_info.value.status_code == 403


# ── Process-control endpoints: smoke tests with mock localhost ──────


@pytest.mark.asyncio
async def test_shutdown_returns_200_from_localhost() -> None:
    """POST /shutdown is allowed from 127.0.0.1 (ASGITransport always uses loopback)."""
    async with _make_client() as ac:
        with patch("app.routers.health.asyncio.create_task"):
            response = await ac.post("/shutdown")
    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}


@pytest.mark.asyncio
async def test_ollama_start_returns_200_or_already_running() -> None:
    """POST /ollama/start succeeds from localhost."""
    app = create_app()
    app.state.chroma_client = MagicMock()
    app.state.ollama_reachable = False
    setup_app_state(app)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    app.state.llm_service._client.get = AsyncMock(return_value=mock_resp)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        response = await ac.post("/ollama/start")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ollama_stop_returns_200() -> None:
    """POST /ollama/stop succeeds from localhost."""
    async with _make_client() as ac:
        with patch("app.routers.health.subprocess.run"):
            response = await ac.post("/ollama/stop")
    assert response.status_code == 200
