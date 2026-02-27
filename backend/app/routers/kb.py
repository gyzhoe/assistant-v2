"""
KB management router — browse, search, and delete knowledge base articles.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.kb import (
    ArticleDeleteResponse,
    ArticleDetailResponse,
    ArticleListResponse,
    ArticleSummary,
    ChunkDetail,
    StatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["kb-management"])

# ── Article index cache ───────────────────────────────────────────────────────
# Module-level dict: article_id → ArticleSummary fields
# Rebuilt from ChromaDB on first access, then cached for _CACHE_TTL seconds.

_CACHE_TTL = 300  # 5 minutes

_article_cache: dict[str, dict[str, Any]] = {}
_cache_timestamp: float = 0.0
_total_chunks_cached: int = 0


def invalidate_article_cache() -> None:
    """Invalidate the article index cache (called after mutations)."""
    global _cache_timestamp
    _cache_timestamp = 0.0


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

        if aid not in index:
            # Determine source: source_file for html/pdf, source_url for url
            source = metadata.get("source_file") or metadata.get("source_url") or ""
            index[aid] = {
                "article_id": aid,
                "title": metadata.get("title", "Untitled"),
                "source_type": metadata.get("source_type", "unknown"),
                "source": source,
                "chunk_count": 0,
                "imported_at": metadata.get("imported_at"),
            }
        index[aid]["chunk_count"] += 1

    return index, total


async def _get_article_index(
    request: Request,
) -> tuple[dict[str, dict[str, Any]], int]:
    """Return the cached article index, rebuilding if stale.

    Returns (index_dict, total_chunks).
    """
    global _article_cache, _cache_timestamp, _total_chunks_cached

    if _is_cache_valid():
        return _article_cache, _total_chunks_cached

    chroma_client = request.app.state.chroma_client

    try:
        col = await asyncio.to_thread(
            chroma_client.get_collection, "kb_articles",
        )
    except (ValueError, Exception):
        # Collection doesn't exist
        _article_cache = {}
        _total_chunks_cached = 0
        _cache_timestamp = time.monotonic()
        return _article_cache, _total_chunks_cached

    result = await asyncio.to_thread(
        col.get, include=["metadatas"],
    )

    ids: list[str] = result.get("ids", [])
    metadatas: list[dict[str, Any]] = result.get("metadatas", [])

    _article_cache, _total_chunks_cached = _build_article_index(ids, metadatas)
    _cache_timestamp = time.monotonic()

    return _article_cache, _total_chunks_cached


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/articles", response_model=ArticleListResponse)
async def list_articles(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    source_type: str | None = None,
) -> ArticleListResponse:
    """List KB articles with pagination, search, and source type filter."""
    index, _ = await _get_article_index(request)

    # Filter
    articles = list(index.values())

    if search:
        search_lower = search.lower()
        articles = [a for a in articles if search_lower in a["title"].lower()]

    if source_type:
        articles = [a for a in articles if a["source_type"] == source_type]

    # Sort by imported_at descending (nulls last)
    articles.sort(
        key=lambda a: a.get("imported_at") or "",
        reverse=True,
    )

    total = len(articles)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_articles = articles[start:end]

    return ArticleListResponse(
        articles=[ArticleSummary(**a) for a in page_articles],
        total_articles=total,
        page=page,
        page_size=page_size,
    )


@router.get("/articles/{article_id}", response_model=ArticleDetailResponse)
async def get_article(request: Request, article_id: str) -> ArticleDetailResponse:
    """Get article detail with all chunks."""
    chroma_client = request.app.state.chroma_client

    try:
        col = await asyncio.to_thread(
            chroma_client.get_collection, "kb_articles",
        )
    except (ValueError, Exception):
        return JSONResponse(  # type: ignore[return-value]
            status_code=404,
            content={"detail": f"Article not found: {article_id}"},
        )

    result = await asyncio.to_thread(
        col.get,
        where={"article_id": article_id},
        include=["documents", "metadatas"],
    )

    ids: list[str] = result.get("ids", [])
    documents: list[str] = result.get("documents", [])
    metadatas: list[dict[str, Any]] = result.get("metadatas", [])

    if not ids:
        return JSONResponse(  # type: ignore[return-value]
            status_code=404,
            content={"detail": f"Article not found: {article_id}"},
        )

    # Build article metadata from first chunk
    first_meta = metadatas[0]
    source = first_meta.get("source_file") or first_meta.get("source_url") or ""

    chunks = [
        ChunkDetail(
            id=chunk_id,
            text=doc,
            section=meta.get("section"),
            metadata=meta,
        )
        for chunk_id, doc, meta in zip(ids, documents, metadatas)
    ]

    return ArticleDetailResponse(
        article_id=article_id,
        title=first_meta.get("title", "Untitled"),
        source_type=first_meta.get("source_type", "unknown"),
        source=source,
        chunk_count=len(ids),
        imported_at=first_meta.get("imported_at"),
        chunks=chunks,
    )


@router.delete("/articles/{article_id}", response_model=ArticleDeleteResponse)
async def delete_article(
    request: Request, article_id: str,
) -> ArticleDeleteResponse:
    """Delete all chunks belonging to an article."""
    chroma_client = request.app.state.chroma_client

    try:
        col = await asyncio.to_thread(
            chroma_client.get_collection, "kb_articles",
        )
    except (ValueError, Exception):
        return JSONResponse(  # type: ignore[return-value]
            status_code=404,
            content={"detail": f"Article not found: {article_id}"},
        )

    # Get chunk IDs for this article
    result = await asyncio.to_thread(
        col.get, where={"article_id": article_id},
    )

    ids: list[str] = result.get("ids", [])

    if not ids:
        return JSONResponse(  # type: ignore[return-value]
            status_code=404,
            content={"detail": f"Article not found: {article_id}"},
        )

    await asyncio.to_thread(col.delete, ids=ids)
    invalidate_article_cache()

    return ArticleDeleteResponse(
        article_id=article_id,
        chunks_deleted=len(ids),
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(request: Request) -> StatsResponse:
    """Return KB collection statistics."""
    index, total_chunks = await _get_article_index(request)

    by_source_type: dict[str, int] = {}
    for article in index.values():
        st = article["source_type"]
        by_source_type[st] = by_source_type.get(st, 0) + 1

    return StatsResponse(
        total_articles=len(index),
        total_chunks=total_chunks,
        by_source_type=by_source_type,
    )
