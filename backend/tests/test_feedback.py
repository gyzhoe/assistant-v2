"""Tests for the feedback endpoint (POST /feedback)."""

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


@pytest.mark.asyncio
@patch("app.routers.feedback.EmbedService")
async def test_feedback_good_returns_204(mock_embed_cls: MagicMock) -> None:
    mock_embed_cls.return_value.embed = AsyncMock(return_value=[0.1] * 768)
    async with _make_client() as ac:
        resp = await ac.post("/feedback", json=_valid_payload("good"))
    assert resp.status_code == 204
    assert resp.content == b""


@pytest.mark.asyncio
@patch("app.routers.feedback.EmbedService")
async def test_feedback_bad_returns_204(mock_embed_cls: MagicMock) -> None:
    mock_embed_cls.return_value.embed = AsyncMock(return_value=[0.1] * 768)
    async with _make_client() as ac:
        resp = await ac.post("/feedback", json=_valid_payload("bad"))
    assert resp.status_code == 204


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
async def test_feedback_chromadb_failure_still_returns_204(
    mock_embed_cls: MagicMock,
) -> None:
    """Even if ChromaDB raises, the endpoint returns 204 (silent failure)."""
    mock_embed_cls.return_value.embed = AsyncMock(side_effect=ConnectionError("boom"))
    async with _make_client() as ac:
        resp = await ac.post("/feedback", json=_valid_payload())
    assert resp.status_code == 204


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

    assert resp.status_code == 204
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
