"""Tests for the feedback endpoints (POST /feedback, DELETE /feedback/{doc_id})."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


def _make_client() -> AsyncClient:
    app = create_app()
    app.state.chroma_client = MagicMock()
    app.state.ollama_reachable = False
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


def _valid_payload(rating: str = "good") -> dict[str, str]:
    return {
        "ticket_subject": "VPN not connecting",
        "ticket_description": "User reports VPN disconnects on startup.",
        "category": "NETWORK CONNECTION",
        "reply": "Hi, try clearing your VPN credentials.",
        "rating": rating,
    }


# ── POST /feedback ─────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.routers.feedback.EmbedService")
async def test_feedback_good_returns_200_with_id(mock_embed_cls: MagicMock) -> None:
    mock_embed_cls.return_value.embed = AsyncMock(return_value=[0.1] * 768)
    async with _make_client() as ac:
        resp = await ac.post("/feedback", json=_valid_payload("good"))
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert body["id"].startswith("rated_")


@pytest.mark.asyncio
@patch("app.routers.feedback.EmbedService")
async def test_feedback_bad_returns_200_with_id(mock_embed_cls: MagicMock) -> None:
    mock_embed_cls.return_value.embed = AsyncMock(return_value=[0.1] * 768)
    async with _make_client() as ac:
        resp = await ac.post("/feedback", json=_valid_payload("bad"))
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert body["id"].startswith("rated_")


@pytest.mark.asyncio
async def test_feedback_invalid_rating_returns_422() -> None:
    async with _make_client() as ac:
        payload = _valid_payload()
        payload["rating"] = "neutral"
        resp = await ac.post("/feedback", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_feedback_missing_required_fields_returns_422() -> None:
    async with _make_client() as ac:
        resp = await ac.post("/feedback", json={"rating": "good"})
    assert resp.status_code == 422


@pytest.mark.asyncio
@patch("app.routers.feedback.EmbedService")
async def test_feedback_connection_failure_returns_503(
    mock_embed_cls: MagicMock,
) -> None:
    """Connection errors (Ollama/ChromaDB down) return 503 Service Unavailable."""
    mock_embed_cls.return_value.embed = AsyncMock(side_effect=ConnectionError("boom"))
    async with _make_client() as ac:
        resp = await ac.post("/feedback", json=_valid_payload())
    assert resp.status_code == 503


@pytest.mark.asyncio
@patch("app.routers.feedback.EmbedService")
async def test_feedback_stores_in_rated_replies_collection(
    mock_embed_cls: MagicMock,
) -> None:
    mock_embed_cls.return_value.embed = AsyncMock(return_value=[0.1] * 768)
    app = create_app()
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_chroma.get_or_create_collection.return_value = mock_col
    app.state.chroma_client = mock_chroma
    app.state.ollama_reachable = False

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post("/feedback", json=_valid_payload("good"))

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"].startswith("rated_")
    mock_chroma.get_or_create_collection.assert_called_once_with(
        name="rated_replies",
        metadata={"hnsw:space": "cosine"},
    )
    mock_col.add.assert_called_once()
    call_kwargs = mock_col.add.call_args
    meta = call_kwargs.kwargs["metadatas"][0] if call_kwargs.kwargs else call_kwargs[1]["metadatas"][0]
    assert meta["rating"] == "good"
    assert meta["category"] == "NETWORK CONNECTION"
    assert meta["ticket_subject"] == "VPN not connecting"
    assert "reply" in meta


# ── DELETE /feedback/{doc_id} ──────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_feedback_returns_204() -> None:
    """Deleting an existing feedback entry returns 204."""
    app = create_app()
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_col.get.return_value = {"ids": ["rated_abc123"]}
    mock_chroma.get_or_create_collection.return_value = mock_col
    app.state.chroma_client = mock_chroma
    app.state.ollama_reachable = False

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.delete("/feedback/rated_abc123")

    assert resp.status_code == 204
    mock_col.delete.assert_called_once_with(ids=["rated_abc123"])


@pytest.mark.asyncio
async def test_delete_feedback_not_found_returns_404() -> None:
    """Deleting a non-existent feedback entry returns 404."""
    app = create_app()
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_col.get.return_value = {"ids": []}
    mock_chroma.get_or_create_collection.return_value = mock_col
    app.state.chroma_client = mock_chroma
    app.state.ollama_reachable = False

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.delete("/feedback/rated_nonexistent")

    assert resp.status_code == 404
    mock_col.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_feedback_connection_failure_returns_503() -> None:
    """ChromaDB connection failure during delete returns 503."""
    app = create_app()
    mock_chroma = MagicMock()
    mock_chroma.get_or_create_collection.side_effect = ConnectionError("down")
    app.state.chroma_client = mock_chroma
    app.state.ollama_reachable = False

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.delete("/feedback/rated_abc123")

    assert resp.status_code == 503
