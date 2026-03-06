"""Tests for the KB article creation endpoint (POST /kb/articles)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.routers import kb as kb_mod
from tests.helpers import setup_app_state


def _mock_embed(text: str) -> list[float]:
    """Deterministic fake embedding for tests."""
    return [0.1] * 384


def _fresh_client(
    collection_data: dict[str, Any] | None = None,
    collection_exists: bool = True,
) -> AsyncClient:
    """Build an AsyncClient with a mocked ChromaDB client."""
    app = create_app()
    mock_chroma = MagicMock()
    mock_col = MagicMock()

    if not collection_exists:
        mock_chroma.get_collection.side_effect = ValueError("Collection not found")
    else:
        mock_chroma.get_collection.return_value = mock_col
        default_data: dict[str, Any] = {
            "ids": [], "documents": [], "metadatas": [],
        }
        mock_col.get.return_value = collection_data or default_data

    mock_chroma.get_or_create_collection.return_value = mock_col
    app.state.chroma_client = mock_chroma
    app.state.llm_reachable = False
    setup_app_state(app)

    # Override sync_embed_service with deterministic embed
    mock_sync_embed = MagicMock()
    mock_sync_embed.embed_fn = _mock_embed
    app.state.sync_embed_service = mock_sync_embed

    # Reset the module-level cache before each test
    kb_mod._article_cache = {}
    kb_mod._cache_timestamp = 0.0
    kb_mod._total_chunks_cached = 0

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Extension-Token": "test-bypass"},
    )


# ---------------------------------------------------------------------------
# POST /kb/articles — create article
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_article_success() -> None:
    mock_col = MagicMock()
    mock_col.get.return_value = {"ids": [], "documents": [], "metadatas": []}

    app = create_app()
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_chroma.get_or_create_collection.return_value = mock_col
    app.state.chroma_client = mock_chroma
    app.state.llm_reachable = False
    setup_app_state(app)

    # Override sync_embed_service with deterministic embed
    mock_sync_embed = MagicMock()
    mock_sync_embed.embed_fn = _mock_embed
    app.state.sync_embed_service = mock_sync_embed

    kb_mod._article_cache = {}
    kb_mod._cache_timestamp = 0.0
    kb_mod._total_chunks_cached = 0

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post("/kb/articles", json={
            "title": "VPN Setup Guide",
            "content": "## Introduction\n\nHow to set up VPN.",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "VPN Setup Guide"
    assert data["article_id"]
    assert data["chunks_ingested"] > 0
    assert data["processing_time_ms"] >= 0

    # Verify upsert was called with correct metadata
    upsert_calls = mock_col.upsert.call_args_list
    assert len(upsert_calls) > 0
    meta = upsert_calls[0].kwargs.get("metadatas") or upsert_calls[0][1].get("metadatas", [])
    assert meta[0]["source_type"] == "manual"
    assert meta[0]["title"] == "VPN Setup Guide"


@pytest.mark.asyncio
async def test_create_article_empty_title() -> None:
    async with _fresh_client() as ac:
        resp = await ac.post("/kb/articles", json={
            "title": "",
            "content": "Some content here.",
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_article_empty_content() -> None:
    async with _fresh_client() as ac:
        resp = await ac.post("/kb/articles", json={
            "title": "A Title",
            "content": "",
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_article_duplicate() -> None:
    """Creating an article with the same title twice should return 409."""
    # Simulate existing article with matching article_id
    existing_data: dict[str, Any] = {
        "ids": ["some_chunk_0"],
        "documents": ["existing content"],
        "metadatas": [{"article_id": "abc123", "title": "VPN Setup Guide"}],
    }

    mock_col = MagicMock()
    mock_col.get.return_value = existing_data

    app = create_app()
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    app.state.chroma_client = mock_chroma
    app.state.llm_reachable = False
    setup_app_state(app)

    kb_mod._article_cache = {}
    kb_mod._cache_timestamp = 0.0
    kb_mod._total_chunks_cached = 0

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post("/kb/articles", json={
            "title": "VPN Setup Guide",
            "content": "## Intro\n\nSome content.",
        })

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_article_heading_sections() -> None:
    """Verify ## headings create correct section names in metadata."""
    mock_col = MagicMock()
    mock_col.get.return_value = {"ids": [], "documents": [], "metadatas": []}

    app = create_app()
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_chroma.get_or_create_collection.return_value = mock_col
    app.state.chroma_client = mock_chroma
    app.state.llm_reachable = False
    setup_app_state(app)

    mock_sync_embed = MagicMock()
    mock_sync_embed.embed_fn = _mock_embed
    app.state.sync_embed_service = mock_sync_embed

    kb_mod._article_cache = {}
    kb_mod._cache_timestamp = 0.0
    kb_mod._total_chunks_cached = 0

    content = (
        "Intro paragraph before headings.\n\n"
        "## Prerequisites\n\nYou need admin access.\n\n"
        "## Steps\n\nStep 1: Open settings.\n\n"
        "### Sub-step\n\nConfigure the network."
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post("/kb/articles", json={
            "title": "Multi-Section Article",
            "content": content,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["chunks_ingested"] == 4  # Intro + Prerequisites + Steps + Sub-step

    # Verify section names in upsert metadata
    upsert_calls = mock_col.upsert.call_args_list
    all_metas: list[dict[str, str]] = []
    for call in upsert_calls:
        metas = call.kwargs.get("metadatas") or call[1].get("metadatas", [])
        all_metas.extend(metas)

    sections = [m["section"] for m in all_metas]
    assert "Introduction" in sections
    assert "Prerequisites" in sections
    assert "Steps" in sections
    assert "Sub-step" in sections


@pytest.mark.asyncio
async def test_create_article_embed_down() -> None:
    """When embed server is unreachable, should return 503."""
    mock_col = MagicMock()
    mock_col.get.return_value = {"ids": [], "documents": [], "metadatas": []}

    app = create_app()
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_chroma.get_or_create_collection.return_value = mock_col
    app.state.chroma_client = mock_chroma
    app.state.llm_reachable = False
    setup_app_state(app)

    def embed_raises(text: str) -> list[float]:
        raise ConnectionError("Embed server unreachable")

    mock_sync_embed = MagicMock()
    mock_sync_embed.embed_fn = embed_raises
    app.state.sync_embed_service = mock_sync_embed

    kb_mod._article_cache = {}
    kb_mod._cache_timestamp = 0.0
    kb_mod._total_chunks_cached = 0

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post("/kb/articles", json={
            "title": "Test Article",
            "content": "## Section\n\nSome content for embedding.",
        })

    assert resp.status_code == 503
    assert "embedding server" in resp.json()["detail"].lower()
