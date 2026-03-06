"""Tests for the KB article edit endpoint (PUT /kb/articles/{article_id})."""

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


def _setup_app(
    collection_data: dict[str, Any] | None = None,
) -> tuple[MagicMock, MagicMock, AsyncClient]:
    """Build an AsyncClient with a mocked ChromaDB client that has article data."""
    app = create_app()
    mock_chroma = MagicMock()
    mock_col = MagicMock()

    mock_chroma.get_collection.return_value = mock_col
    mock_chroma.get_or_create_collection.return_value = mock_col

    default_data: dict[str, Any] = {
        "ids": ["art1_chunk_0", "art1_chunk_1"],
        "documents": ["Introduction text.", "## Steps\n\nStep 1."],
        "metadatas": [
            {
                "article_id": "art1",
                "title": "VPN Setup Guide",
                "section": "Introduction",
                "source_type": "manual",
                "imported_at": "2026-02-28T12:00:00+00:00",
                "tags": "NETWORK",
            },
            {
                "article_id": "art1",
                "title": "VPN Setup Guide",
                "section": "Steps",
                "source_type": "manual",
                "imported_at": "2026-02-28T12:00:00+00:00",
                "tags": "NETWORK",
            },
        ],
    }
    mock_col.get.return_value = collection_data or default_data

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

    return mock_chroma, mock_col, AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Extension-Token": "test-bypass"},
    )


# ---------------------------------------------------------------------------
# PUT /kb/articles/{article_id} — update article
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_article_success() -> None:
    _, mock_col, ac = _setup_app()

    async with ac:
        resp = await ac.put("/kb/articles/art1", json={
            "title": "VPN Setup Guide v2",
            "content": "## Introduction\n\nUpdated VPN guide.\n\n## New Steps\n\nStep A.",
            "tags": ["NETWORK", "VPN"],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["article_id"] == "art1"
    assert data["title"] == "VPN Setup Guide v2"
    assert data["chunks_ingested"] > 0
    assert data["processing_time_ms"] >= 0

    # M5: upsert-then-delete — new chunks upserted first, then stale
    # old chunks removed. Here both old IDs (art1_chunk_0, art1_chunk_1)
    # match the new IDs, so no stale deletion is needed.
    upsert_calls = mock_col.upsert.call_args_list
    assert len(upsert_calls) > 0


@pytest.mark.asyncio
async def test_update_article_not_found() -> None:
    _, mock_col, ac = _setup_app(
        collection_data={"ids": [], "documents": [], "metadatas": []},
    )

    async with ac:
        resp = await ac.put("/kb/articles/nonexistent", json={
            "title": "Whatever",
            "content": "Some content.",
            "tags": [],
        })

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_article_non_manual() -> None:
    """Editing an imported (non-manual) article should return 403."""
    _, _, ac = _setup_app(
        collection_data={
            "ids": ["pdf_chunk_0"],
            "documents": ["PDF content here."],
            "metadatas": [{
                "article_id": "pdf1",
                "title": "Imported PDF",
                "section": "Introduction",
                "source_type": "pdf",
                "imported_at": "2026-02-28T12:00:00+00:00",
                "tags": "",
            }],
        },
    )

    async with ac:
        resp = await ac.put("/kb/articles/pdf1", json={
            "title": "Edited PDF",
            "content": "New content.",
            "tags": [],
        })

    assert resp.status_code == 403
    assert "manual" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_article_preserves_id() -> None:
    """article_id must remain the same after edit."""
    _, mock_col, ac = _setup_app()

    async with ac:
        resp = await ac.put("/kb/articles/art1", json={
            "title": "Completely New Title",
            "content": "## New\n\nNew content.",
            "tags": [],
        })

    assert resp.status_code == 200
    assert resp.json()["article_id"] == "art1"

    # Verify chunks use original article_id in metadata
    upsert_calls = mock_col.upsert.call_args_list
    for call in upsert_calls:
        metas = call.kwargs.get("metadatas") or call[1].get("metadatas", [])
        for m in metas:
            assert m["article_id"] == "art1"


@pytest.mark.asyncio
async def test_update_article_preserves_imported_at() -> None:
    """imported_at timestamp must be preserved from the original article."""
    _, mock_col, ac = _setup_app()

    async with ac:
        resp = await ac.put("/kb/articles/art1", json={
            "title": "Updated Title",
            "content": "## Updated\n\nContent.",
            "tags": [],
        })

    assert resp.status_code == 200

    upsert_calls = mock_col.upsert.call_args_list
    for call in upsert_calls:
        metas = call.kwargs.get("metadatas") or call[1].get("metadatas", [])
        for m in metas:
            assert m["imported_at"] == "2026-02-28T12:00:00+00:00"


@pytest.mark.asyncio
async def test_update_article_validation_empty_title() -> None:
    _, _, ac = _setup_app()

    async with ac:
        resp = await ac.put("/kb/articles/art1", json={
            "title": "",
            "content": "Some content.",
            "tags": [],
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_article_validation_invalid_tags() -> None:
    _, _, ac = _setup_app()

    async with ac:
        resp = await ac.put("/kb/articles/art1", json={
            "title": "Valid Title",
            "content": "Valid content.",
            "tags": ["tag,with,comma"],
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_article_rechunks() -> None:
    """Content with more headings should produce more chunks."""
    _, mock_col, ac = _setup_app()

    async with ac:
        resp = await ac.put("/kb/articles/art1", json={
            "title": "Multi-Section",
            "content": (
                "Intro paragraph.\n\n"
                "## Section A\n\nContent A.\n\n"
                "## Section B\n\nContent B.\n\n"
                "## Section C\n\nContent C."
            ),
            "tags": [],
        })

    assert resp.status_code == 200
    assert resp.json()["chunks_ingested"] == 4  # Intro + A + B + C


@pytest.mark.asyncio
async def test_update_article_updates_tags() -> None:
    """New tags should appear in chunk metadata after edit."""
    _, mock_col, ac = _setup_app()

    async with ac:
        resp = await ac.put("/kb/articles/art1", json={
            "title": "Tagged Article",
            "content": "## Content\n\nSome text.",
            "tags": ["VPN", "REMOTE ACCESS"],
        })

    assert resp.status_code == 200

    upsert_calls = mock_col.upsert.call_args_list
    for call in upsert_calls:
        metas = call.kwargs.get("metadatas") or call[1].get("metadatas", [])
        for m in metas:
            assert m["tags"] == "VPN,REMOTE ACCESS"


@pytest.mark.asyncio
async def test_update_article_deletes_stale_chunks() -> None:
    """When new content has fewer chunks, stale old chunks are deleted."""
    # Old article has 3 chunks; new content produces 1 chunk.
    _, mock_col, ac = _setup_app(
        collection_data={
            "ids": ["art1_chunk_0", "art1_chunk_1", "art1_chunk_2"],
            "documents": ["A", "B", "C"],
            "metadatas": [
                {
                    "article_id": "art1",
                    "title": "Old",
                    "section": "S0",
                    "source_type": "manual",
                    "imported_at": "2026-02-28T12:00:00+00:00",
                    "tags": "",
                },
                {
                    "article_id": "art1",
                    "title": "Old",
                    "section": "S1",
                    "source_type": "manual",
                    "imported_at": "2026-02-28T12:00:00+00:00",
                    "tags": "",
                },
                {
                    "article_id": "art1",
                    "title": "Old",
                    "section": "S2",
                    "source_type": "manual",
                    "imported_at": "2026-02-28T12:00:00+00:00",
                    "tags": "",
                },
            ],
        },
    )

    async with ac:
        resp = await ac.put("/kb/articles/art1", json={
            "title": "Smaller",
            "content": "Single paragraph, no headings.",
            "tags": [],
        })

    assert resp.status_code == 200
    assert resp.json()["chunks_ingested"] == 1

    # Stale chunks (art1_chunk_1, art1_chunk_2) should be deleted
    mock_col.delete.assert_called_once()
    deleted_ids = mock_col.delete.call_args[1].get(
        "ids",
    ) or mock_col.delete.call_args[0][0]
    assert set(deleted_ids) == {"art1_chunk_1", "art1_chunk_2"}


@pytest.mark.asyncio
async def test_update_article_collection_not_found() -> None:
    """If KB collection doesn't exist, return 404."""
    app = create_app()
    mock_chroma = MagicMock()
    mock_chroma.get_collection.side_effect = ValueError("Collection not found")
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
        resp = await ac.put("/kb/articles/any_id", json={
            "title": "Title",
            "content": "Content.",
            "tags": [],
        })

    assert resp.status_code == 404
