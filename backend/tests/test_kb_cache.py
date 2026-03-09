"""Tests for the KB cache service (app.services.kb_cache)."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services import kb_cache as kb_cache_mod
from app.services.kb_cache import (
    _build_article_index,
    _get_article_chunks,
    _get_article_index,
    _is_cache_valid,
    _rebuild_article_cache,
    invalidate_article_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Reset module-level cache state before each test."""
    kb_cache_mod._article_cache = {}
    kb_cache_mod._cache_timestamp = 0.0
    kb_cache_mod._total_chunks_cached = 0
    kb_cache_mod._refresh_in_progress = False


# ---------------------------------------------------------------------------
# _is_cache_valid
# ---------------------------------------------------------------------------


def test_is_cache_valid_returns_false_initially() -> None:
    """Cache is invalid when timestamp is 0 (never populated)."""
    assert _is_cache_valid() is False


def test_is_cache_valid_returns_true_after_set() -> None:
    """Cache is valid right after setting a recent timestamp."""
    kb_cache_mod._cache_timestamp = time.monotonic()
    assert _is_cache_valid() is True


def test_is_cache_valid_returns_false_after_expiry() -> None:
    """Cache is invalid once TTL has elapsed."""
    kb_cache_mod._cache_timestamp = time.monotonic() - kb_cache_mod._CACHE_TTL - 1
    assert _is_cache_valid() is False


# ---------------------------------------------------------------------------
# invalidate_article_cache
# ---------------------------------------------------------------------------


def test_invalidate_resets_timestamp() -> None:
    """invalidate_article_cache resets timestamp to 0."""
    kb_cache_mod._cache_timestamp = time.monotonic()
    kb_cache_mod._refresh_in_progress = True
    invalidate_article_cache()
    assert kb_cache_mod._cache_timestamp == 0.0
    assert kb_cache_mod._refresh_in_progress is False


# ---------------------------------------------------------------------------
# _build_article_index
# ---------------------------------------------------------------------------


def test_build_article_index_groups_chunks() -> None:
    """Chunks with the same article_id are grouped together."""
    ids = ["c1", "c2", "c3"]
    metadatas: list[dict[str, Any]] = [
        {
            "article_id": "a1", "title": "Article One",
            "source_type": "html", "source_file": "one.html",
            "imported_at": "2026-01-01", "tags": "net",
        },
        {
            "article_id": "a1", "title": "Article One",
            "source_type": "html", "source_file": "one.html",
            "imported_at": "2026-01-01", "tags": "vpn",
        },
        {
            "article_id": "a2", "title": "Article Two",
            "source_type": "pdf", "source_file": "two.pdf",
            "imported_at": "2026-01-02", "tags": "",
        },
    ]

    index, total = _build_article_index(ids, metadatas)

    assert total == 3
    assert len(index) == 2
    assert index["a1"]["chunk_count"] == 2
    assert index["a2"]["chunk_count"] == 1


def test_build_article_index_merges_tags() -> None:
    """Tags across chunks of the same article are merged (union)."""
    ids = ["c1", "c2"]
    metadatas: list[dict[str, Any]] = [
        {
            "article_id": "a1", "title": "T",
            "source_type": "html", "source_file": "f",
            "imported_at": "2026-01-01", "tags": "alpha,beta",
        },
        {
            "article_id": "a1", "title": "T",
            "source_type": "html", "source_file": "f",
            "imported_at": "2026-01-01", "tags": "beta,gamma",
        },
    ]

    index, _ = _build_article_index(ids, metadatas)

    assert sorted(index["a1"]["tags"]) == ["alpha", "beta", "gamma"]


def test_build_article_index_skips_empty_article_id() -> None:
    """Chunks without an article_id are skipped."""
    ids = ["c1"]
    metadatas: list[dict[str, Any]] = [
        {"article_id": "", "title": "Orphan", "tags": ""},
    ]

    index, total = _build_article_index(ids, metadatas)

    assert total == 1
    assert len(index) == 0


def test_build_article_index_uses_source_url() -> None:
    """URL-sourced articles use source_url instead of source_file."""
    ids = ["c1"]
    metadatas: list[dict[str, Any]] = [
        {
            "article_id": "u1", "title": "URL Article",
            "source_type": "url", "source_url": "https://example.com",
            "imported_at": "2026-01-01", "tags": "",
        },
    ]

    index, _ = _build_article_index(ids, metadatas)

    assert index["u1"]["source"] == "https://example.com"


# ---------------------------------------------------------------------------
# _rebuild_article_cache (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_cache_populates_state() -> None:
    """_rebuild_article_cache should populate module-level cache state."""
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_col.get.return_value = {
        "ids": ["c1", "c2"],
        "metadatas": [
            {
                "article_id": "a1", "title": "T",
                "source_type": "html", "source_file": "f",
                "imported_at": "2026-01-01", "tags": "",
            },
            {
                "article_id": "a1", "title": "T",
                "source_type": "html", "source_file": "f",
                "imported_at": "2026-01-01", "tags": "",
            },
        ],
    }

    await _rebuild_article_cache(mock_chroma)

    assert len(kb_cache_mod._article_cache) == 1
    assert kb_cache_mod._total_chunks_cached == 2
    assert kb_cache_mod._cache_timestamp > 0


@pytest.mark.asyncio
async def test_rebuild_cache_handles_missing_collection() -> None:
    """When the collection doesn't exist, cache is set to empty."""
    mock_chroma = MagicMock()
    mock_chroma.get_collection.side_effect = ValueError("not found")

    await _rebuild_article_cache(mock_chroma)

    assert kb_cache_mod._article_cache == {}
    assert kb_cache_mod._total_chunks_cached == 0
    assert kb_cache_mod._cache_timestamp > 0  # still set (prevents retry storm)


# ---------------------------------------------------------------------------
# _get_article_index (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_article_index_cold_cache() -> None:
    """On cold cache (first call), blocks until data is ready."""
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_col.get.return_value = {
        "ids": ["c1"],
        "metadatas": [
            {
                "article_id": "a1", "title": "T",
                "source_type": "html", "source_file": "f",
                "imported_at": "2026-01-01", "tags": "",
            },
        ],
    }

    index, total = await _get_article_index(mock_chroma)

    assert len(index) == 1
    assert total == 1


@pytest.mark.asyncio
async def test_get_article_index_warm_cache() -> None:
    """Warm cache is returned without hitting ChromaDB."""
    mock_chroma = MagicMock()

    # Pre-warm cache
    kb_cache_mod._article_cache = {"a1": {"title": "Cached"}}
    kb_cache_mod._total_chunks_cached = 5
    kb_cache_mod._cache_timestamp = time.monotonic()

    index, total = await _get_article_index(mock_chroma)

    assert index == {"a1": {"title": "Cached"}}
    assert total == 5
    # ChromaDB should not be called
    mock_chroma.get_collection.assert_not_called()


# ---------------------------------------------------------------------------
# _get_article_chunks (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_article_chunks_success() -> None:
    """Fetching chunks for an existing article returns data."""
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_col.get.return_value = {
        "ids": ["c1", "c2"],
        "metadatas": [
            {"article_id": "a1", "title": "T"},
            {"article_id": "a1", "title": "T"},
        ],
    }

    col, ids, metadatas, result = await _get_article_chunks(mock_chroma, "a1")

    assert ids == ["c1", "c2"]
    assert len(metadatas) == 2


@pytest.mark.asyncio
async def test_get_article_chunks_not_found() -> None:
    """Fetching a nonexistent article raises HTTPException 404."""
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_col.get.return_value = {"ids": [], "metadatas": []}

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await _get_article_chunks(mock_chroma, "nonexistent")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_article_chunks_collection_missing() -> None:
    """Missing collection raises HTTPException 404."""
    mock_chroma = MagicMock()
    mock_chroma.get_collection.side_effect = ValueError("not found")

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await _get_article_chunks(mock_chroma, "any")

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Concurrent access / lock behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_cache_triggers_background_refresh() -> None:
    """When cache is stale but populated, it returns stale data
    and schedules a background refresh."""
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_col.get.return_value = {
        "ids": ["c1"],
        "metadatas": [
            {
                "article_id": "a1", "title": "Fresh",
                "source_type": "html", "source_file": "f",
                "imported_at": "2026-01-01", "tags": "",
            },
        ],
    }

    # Pre-warm with stale data
    kb_cache_mod._article_cache = {"a1": {"title": "Stale"}}
    kb_cache_mod._total_chunks_cached = 1
    kb_cache_mod._cache_timestamp = (
        time.monotonic() - kb_cache_mod._CACHE_TTL - 1
    )

    with patch("app.services.kb_cache.asyncio.create_task") as mock_task:
        index, total = await _get_article_index(mock_chroma)

    # Should return stale data immediately
    assert index["a1"]["title"] == "Stale"
    # Should have scheduled a background refresh
    mock_task.assert_called_once()
