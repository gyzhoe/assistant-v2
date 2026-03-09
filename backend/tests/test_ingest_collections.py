"""Tests for the /ingest/collections/{name}/clear endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


def _make_client() -> AsyncClient:
    fresh_app = create_app()
    fresh_app.state.chroma_client = MagicMock()
    fresh_app.state.llm_reachable = False
    return AsyncClient(
        transport=ASGITransport(app=fresh_app),
        base_url="http://testserver",
        headers={"X-Extension-Token": "test-bypass"},
    )


@pytest.mark.asyncio
async def test_clear_kb_articles_returns_ok() -> None:
    async with _make_client() as ac:
        resp = await ac.post("/ingest/collections/kb_articles/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["collection"] == "kb_articles"


@pytest.mark.asyncio
async def test_clear_whd_tickets_returns_ok() -> None:
    async with _make_client() as ac:
        resp = await ac.post("/ingest/collections/whd_tickets/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["collection"] == "whd_tickets"


@pytest.mark.asyncio
async def test_clear_invalid_collection_returns_422() -> None:
    async with _make_client() as ac:
        resp = await ac.post("/ingest/collections/nonexistent/clear")
        assert resp.status_code == 422
        assert "Unknown collection" in resp.json()["message"]


@pytest.mark.asyncio
async def test_clear_idempotent() -> None:
    """Clearing a collection twice should both return 200."""
    fresh_app = create_app()
    mock_client = MagicMock()
    fresh_app.state.chroma_client = mock_client
    fresh_app.state.llm_reachable = False

    # First call succeeds normally
    # Second call: delete_collection raises ValueError (already deleted)
    mock_client.delete_collection.side_effect = [None, ValueError("not found")]

    async with AsyncClient(
        transport=ASGITransport(app=fresh_app),
        base_url="http://testserver",
        headers={"X-Extension-Token": "test-bypass"},
    ) as ac:
        resp1 = await ac.post("/ingest/collections/kb_articles/clear")
        assert resp1.status_code == 200

        resp2 = await ac.post("/ingest/collections/kb_articles/clear")
        assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_clear_requires_api_token_when_configured() -> None:
    """When API_TOKEN is set, /ingest/collections/*/clear requires the token."""
    from unittest.mock import patch

    with (
        patch("app.config.settings.api_token", "test-secret-token"),
        patch("app.config.settings.cors_origin", "chrome-extension://test"),
    ):
        fresh_app = create_app()
        fresh_app.state.chroma_client = MagicMock()
        fresh_app.state.llm_reachable = False

        async with AsyncClient(
            transport=ASGITransport(app=fresh_app),
            base_url="http://testserver",
        ) as ac:
            # Wrong token (not empty — bypasses CSRF, but fails auth) → 401
            resp = await ac.post(
                "/ingest/collections/kb_articles/clear",
                headers={"X-Extension-Token": "wrong-token"},
            )
            assert resp.status_code == 401

            # With correct token → 200
            resp = await ac.post(
                "/ingest/collections/kb_articles/clear",
                headers={"X-Extension-Token": "test-secret-token"},
            )
            assert resp.status_code == 200
