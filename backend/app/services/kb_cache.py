"""KB article cache — manages the in-memory article index built from ChromaDB.

Extracted from ``app.routers.kb`` to decouple cache state from the router
module and eliminate a cross-router import in ``app.routers.ingest``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

from chromadb.api import ClientAPI
from fastapi import HTTPException

from app.constants import KB_COLLECTION, parse_tags

# ── Article index cache ───────────────────────────────────────────────────────
# Module-level dict: article_id → ArticleSummary fields
# Rebuilt from ChromaDB on first access, then cached for _CACHE_TTL seconds.

_CACHE_TTL = 300  # 5 minutes

_article_cache: dict[str, dict[str, Any]] = {}
_cache_timestamp: float = 0.0
_total_chunks_cached: int = 0
_cache_lock = asyncio.Lock()
_refresh_in_progress = False


def invalidate_article_cache() -> None:
    """Invalidate the article index cache (called after mutations)."""
    global _cache_timestamp, _refresh_in_progress
    _cache_timestamp = 0.0
    _refresh_in_progress = False


def _is_cache_valid() -> bool:
    return _cache_timestamp > 0 and (time.monotonic() - _cache_timestamp) < _CACHE_TTL


def _build_article_index(
    ids: list[str], metadatas: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], int]:
    """Group chunks by article_id and build the index.

    Returns (index_dict, total_chunks).
    """
    index: dict[str, dict[str, Any]] = {}
    total = len(ids)

    for metadata in metadatas:
        aid = metadata.get("article_id", "")
        if not aid:
            continue

        chunk_tags = parse_tags(metadata.get("tags", ""))

        if aid not in index:
            # Determine source: source_file for html/pdf, source_url for url
            source = (
                metadata.get("source_file")
                or metadata.get("source_url")
                or ""
            )
            index[aid] = {
                "article_id": aid,
                "title": metadata.get("title", "Untitled"),
                "source_type": metadata.get("source_type", "unknown"),
                "source": source,
                "chunk_count": 0,
                "imported_at": metadata.get("imported_at"),
                "tags": list(chunk_tags),
            }
        else:
            # Merge tags from additional chunks (union)
            existing_tags: set[str] = set(index[aid].get("tags", []))
            existing_tags.update(chunk_tags)
            index[aid]["tags"] = sorted(existing_tags)
        index[aid]["chunk_count"] += 1

    return index, total


async def _rebuild_article_cache(chroma_client: ClientAPI) -> None:
    """Rebuild the article index from ChromaDB (runs in background or inline).

    Acquires _cache_lock to ensure global mutations are serialised.
    """
    global _article_cache, _cache_timestamp
    global _total_chunks_cached, _refresh_in_progress

    async with _cache_lock:
        try:
            col = await asyncio.to_thread(
                chroma_client.get_collection, KB_COLLECTION,
            )
        except (ValueError, Exception):
            _article_cache = {}
            _total_chunks_cached = 0
            _cache_timestamp = time.monotonic()
            return
        finally:
            _refresh_in_progress = False

        result = await asyncio.to_thread(
            col.get, include=["metadatas"],
        )

        ids: list[str] = result.get("ids", [])
        metadatas = cast(
            list[dict[str, Any]], result.get("metadatas", []),
        )

        new_cache, new_total = _build_article_index(ids, metadatas)

        _article_cache = new_cache
        _total_chunks_cached = new_total
        _cache_timestamp = time.monotonic()
        _refresh_in_progress = False


async def _get_article_index(
    chroma_client: ClientAPI,
) -> tuple[dict[str, dict[str, Any]], int]:
    """Return the cached article index, rebuilding if stale.

    If a stale cache exists, returns it immediately and schedules a
    background refresh so that callers are never blocked by ChromaDB I/O.
    On the very first call (cold cache), blocks until data is ready.

    Returns (index_dict, total_chunks).
    """
    global _refresh_in_progress

    if _is_cache_valid():
        return _article_cache, _total_chunks_cached

    # Stale but populated cache: serve stale, refresh in background
    if _article_cache and not _refresh_in_progress:
        _refresh_in_progress = True
        asyncio.create_task(_rebuild_article_cache(chroma_client))
        return _article_cache, _total_chunks_cached

    # Cold cache (first call): must block until data is ready
    await _rebuild_article_cache(chroma_client)
    return _article_cache, _total_chunks_cached


# ── Shared article lookup ─────────────────────────────────────────────────────


async def _get_article_chunks(
    chroma_client: ClientAPI,
    article_id: str,
    include: list[Any] | None = None,
) -> tuple[Any, list[str], list[dict[str, Any]], Any]:
    """Fetch all chunks for an article; raise 404 if not found.

    Returns (collection, chunk_ids, metadatas, raw_result).
    """
    try:
        col = await asyncio.to_thread(
            chroma_client.get_collection, KB_COLLECTION,
        )
    except (ValueError, Exception) as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Article not found: {article_id}",
        ) from exc

    result = await asyncio.to_thread(
        col.get,
        where={"article_id": article_id},
        include=include or ["metadatas"],
    )

    ids: list[str] = result.get("ids", [])
    metadatas = cast(list[dict[str, Any]], result.get("metadatas", []))

    if not ids:
        raise HTTPException(
            status_code=404,
            detail=f"Article not found: {article_id}",
        )

    return col, ids, metadatas, result
