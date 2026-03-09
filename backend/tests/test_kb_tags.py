"""Tests for KB article tagging: PATCH /kb/articles/{id}/tags, GET /kb/tags,
POST /kb/articles with tags, and RAG filtered retrieval."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.services import kb_cache as kb_cache_mod
from app.services.embed_service import EmbedService
from app.services.rag_service import RAGService
from tests.helpers import setup_app_state


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

    # Reset the module-level cache before each test
    kb_cache_mod._article_cache = {}
    kb_cache_mod._cache_timestamp = 0.0
    kb_cache_mod._total_chunks_cached = 0

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Extension-Token": "test-bypass"},
    )


def _mock_embed(text: str) -> list[float]:
    """Deterministic fake embedding for tests."""
    return [0.1] * 384


# ---------------------------------------------------------------------------
# PATCH /kb/articles/{article_id}/tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tags_success() -> None:
    """Update tags on an article with existing chunks."""
    col_data: dict[str, Any] = {
        "ids": ["c1", "c2"],
        "metadatas": [
            {"article_id": "art1", "title": "VPN Guide", "tags": ""},
            {"article_id": "art1", "title": "VPN Guide", "tags": ""},
        ],
    }
    async with _fresh_client(col_data) as ac:
        resp = await ac.patch("/kb/articles/art1/tags", json={
            "tags": ["network", "vpn"],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["article_id"] == "art1"
    assert data["tags"] == ["network", "vpn"]
    assert data["chunks_updated"] == 2


@pytest.mark.asyncio
async def test_update_tags_not_found() -> None:
    """Updating tags on a non-existent article returns 404."""
    empty: dict[str, Any] = {"ids": [], "metadatas": []}
    async with _fresh_client(empty) as ac:
        resp = await ac.patch("/kb/articles/nonexistent/tags", json={
            "tags": ["test"],
        })

    assert resp.status_code == 404
    assert "not found" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_update_tags_empty() -> None:
    """Passing empty tags list should succeed (clears tags)."""
    col_data: dict[str, Any] = {
        "ids": ["c1"],
        "metadatas": [
            {"article_id": "art1", "title": "Guide", "tags": "old,tags"},
        ],
    }
    async with _fresh_client(col_data) as ac:
        resp = await ac.patch("/kb/articles/art1/tags", json={
            "tags": [],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["tags"] == []
    assert data["chunks_updated"] == 1


@pytest.mark.asyncio
async def test_update_tags_collection_missing() -> None:
    """Updating tags when collection doesn't exist returns 404."""
    async with _fresh_client(collection_exists=False) as ac:
        resp = await ac.patch("/kb/articles/any/tags", json={
            "tags": ["test"],
        })

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_tags_invalidates_cache() -> None:
    """After updating tags, the cache should be invalidated."""
    col_data: dict[str, Any] = {
        "ids": ["c1"],
        "metadatas": [
            {"article_id": "art1", "title": "Guide", "tags": ""},
        ],
    }
    async with _fresh_client(col_data) as ac:
        # Pre-warm cache
        kb_cache_mod._cache_timestamp = 1.0
        kb_cache_mod._article_cache = {"art1": {"title": "test"}}

        await ac.patch("/kb/articles/art1/tags", json={"tags": ["new"]})

        assert kb_cache_mod._cache_timestamp == 0.0


# ---------------------------------------------------------------------------
# GET /kb/tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tags_returns_unique() -> None:
    """Tags endpoint returns deduplicated, sorted tags from all articles."""
    col_data: dict[str, Any] = {
        "ids": ["c1", "c2", "c3"],
        "metadatas": [
            {"article_id": "art1", "title": "A", "source_type": "html",
             "source_file": "a.html", "imported_at": "2026-01-01", "tags": "network,vpn"},
            {"article_id": "art2", "title": "B", "source_type": "html",
             "source_file": "b.html", "imported_at": "2026-01-02", "tags": "vpn,printing"},
            {"article_id": "art3", "title": "C", "source_type": "pdf",
             "source_file": "c.pdf", "imported_at": "2026-01-03", "tags": "network"},
        ],
    }
    async with _fresh_client(col_data) as ac:
        resp = await ac.get("/kb/tags")

    assert resp.status_code == 200
    data = resp.json()
    assert data["tags"] == ["network", "printing", "vpn"]


@pytest.mark.asyncio
async def test_get_tags_empty() -> None:
    """No articles means empty tags list."""
    async with _fresh_client() as ac:
        resp = await ac.get("/kb/tags")

    assert resp.status_code == 200
    data = resp.json()
    assert data["tags"] == []


# ---------------------------------------------------------------------------
# POST /kb/articles with tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_article_with_tags() -> None:
    """Creating an article with tags stores them in chunk metadata."""
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

    kb_cache_mod._article_cache = {}
    kb_cache_mod._cache_timestamp = 0.0
    kb_cache_mod._total_chunks_cached = 0

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post("/kb/articles", json={
            "title": "Tagged Article",
            "content": "## Section\n\nSome content here.",
            "tags": ["network", "vpn"],
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Tagged Article"

    # Verify tags in upsert metadata
    upsert_calls = mock_col.upsert.call_args_list
    assert len(upsert_calls) > 0
    meta = upsert_calls[0].kwargs.get("metadatas") or upsert_calls[0][1].get("metadatas", [])
    assert meta[0]["tags"] == "network,vpn"


# ---------------------------------------------------------------------------
# Tag validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tags_reject_commas() -> None:
    """Tags containing commas are rejected (comma is the storage delimiter)."""
    async with _fresh_client() as ac:
        resp = await ac.patch("/kb/articles/art1/tags", json={
            "tags": ["NETWORK,CONNECTION"],
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tags_strip_whitespace_and_drop_empty() -> None:
    """Whitespace-only and padded tags are cleaned up."""
    col_data: dict[str, Any] = {
        "ids": ["c1"],
        "metadatas": [
            {"article_id": "art1", "title": "Guide", "tags": ""},
        ],
    }
    async with _fresh_client(col_data) as ac:
        resp = await ac.patch("/kb/articles/art1/tags", json={
            "tags": ["  network  ", "", "  ", "vpn"],
        })

    assert resp.status_code == 200
    data = resp.json()
    # Empty/whitespace tags dropped, remaining stripped
    assert data["tags"] == ["network", "vpn"]


# ---------------------------------------------------------------------------
# RAG filtered retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rag_retrieve_with_category() -> None:
    """With category, RAG should pass where clause to KB collection query."""
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_col.count.return_value = 10
    mock_col.query.return_value = {
        "documents": [["doc1", "doc2"]],
        "metadatas": [[{"article_id": "a1", "tags": "network"}, {"article_id": "a2"}]],
        "distances": [[0.1, 0.3]],
    }
    mock_chroma.get_collection.return_value = mock_col

    mock_embed_svc = MagicMock(spec=EmbedService)
    mock_embed_svc.embed = AsyncMock(return_value=[0.1] * 384)
    rag = RAGService(chroma_client=mock_chroma, embed_svc=mock_embed_svc)

    results = await rag.retrieve("test query", max_docs=5, category="network")

    assert len(results) > 0

    # Verify that at least one KB query used the where clause
    query_calls = mock_col.query.call_args_list
    where_used = any(
        call.kwargs.get("where") == {"tags": {"$contains": "network"}}
        for call in query_calls
    )
    assert where_used, "Expected a KB query with where={'tags': {'$contains': 'network'}}"


@pytest.mark.asyncio
async def test_rag_retrieve_without_category() -> None:
    """Without category, RAG should NOT pass where clause (existing behavior)."""
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_col.count.return_value = 10
    mock_col.query.return_value = {
        "documents": [["doc1"]],
        "metadatas": [[{"article_id": "a1"}]],
        "distances": [[0.2]],
    }
    mock_chroma.get_collection.return_value = mock_col

    mock_embed_svc = MagicMock(spec=EmbedService)
    mock_embed_svc.embed = AsyncMock(return_value=[0.1] * 384)
    rag = RAGService(chroma_client=mock_chroma, embed_svc=mock_embed_svc)

    results = await rag.retrieve("test query", max_docs=5, category="")

    assert len(results) > 0

    # Verify no query used a where clause
    query_calls = mock_col.query.call_args_list
    for call in query_calls:
        assert "where" not in call.kwargs, "Expected no where clause without category"
