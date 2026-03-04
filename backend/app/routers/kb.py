"""
KB management router — browse, search, and delete knowledge base articles.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast

from chromadb.api import ClientAPI
from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.models.kb import (
    ArticleDeleteResponse,
    ArticleDetailResponse,
    ArticleListResponse,
    ArticleSummary,
    ChunkDetail,
    CreateArticleResponse,
    StatsResponse,
    TagListResponse,
    UpdateArticleResponse,
    UpdateTagsResponse,
)
from app.models.request_models import (
    CreateArticleRequest,
    UpdateArticleRequest,
    UpdateTagsRequest,
)
from app.routers.shared import upload_semaphore
from app.services.audit import audit_log
from app.utils.chunker import chunk_by_markdown_headings
from ingestion.pipeline import KB_COLLECTION, IngestionPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["kb-management"])

# ── Article index cache ───────────────────────────────────────────────────────
# Module-level dict: article_id → ArticleSummary fields
# Rebuilt from ChromaDB on first access, then cached for _CACHE_TTL seconds.

_CACHE_TTL = 300  # 5 minutes

_article_cache: dict[str, dict[str, Any]] = {}
_cache_timestamp: float = 0.0
_total_chunks_cached: int = 0
_cache_lock = asyncio.Lock()


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

        tags_str = metadata.get("tags", "")
        chunk_tags = (
            [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        )

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
                "tags": list(chunk_tags),
            }
        else:
            # Merge tags from additional chunks (union)
            existing_tags: set[str] = set(index[aid].get("tags", []))
            existing_tags.update(chunk_tags)
            index[aid]["tags"] = sorted(existing_tags)
        index[aid]["chunk_count"] += 1

    return index, total


_refresh_in_progress = False


async def _rebuild_article_cache(chroma_client: ClientAPI) -> None:
    """Rebuild the article index from ChromaDB (runs in background or inline).

    Acquires _cache_lock to ensure global mutations are serialised.
    """
    global _article_cache, _cache_timestamp, _total_chunks_cached, _refresh_in_progress

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


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/articles", response_model=ArticleListResponse)
async def list_articles(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    source_type: str | None = None,
) -> ArticleListResponse:
    """List KB articles with pagination, search, and source type filter."""
    index, _ = await _get_article_index(request.app.state.chroma_client)

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


@router.post("/articles", response_model=CreateArticleResponse)
async def create_article(
    request: Request, body: CreateArticleRequest,
) -> CreateArticleResponse:
    """Create a new KB article from markdown content."""
    # Generate article_id from truncated SHA-256 of title + source marker.
    # 16 hex chars = 64 bits → collision probability ~1 in 2^32 at 2^32
    # documents (birthday paradox). Checked below before insert.
    article_id = hashlib.sha256(
        (body.title + "manual").encode(),
    ).hexdigest()[:16]

    # Check for duplicate title or hash collision
    chroma_client = request.app.state.chroma_client
    try:
        col = await asyncio.to_thread(
            chroma_client.get_collection, KB_COLLECTION,
        )
        existing = await asyncio.to_thread(
            col.get,
            where={"article_id": article_id},
            limit=1,
            include=["metadatas"],
        )
        if existing.get("ids"):
            existing_meta = existing.get("metadatas", [{}])[0]
            existing_title = existing_meta.get("title", "")
            if existing_title == body.title:
                raise HTTPException(
                    status_code=409,
                    detail="An article with this title already exists.",
                )
            # Hash collision — different title, same article_id
            raise HTTPException(
                status_code=409,
                detail=(
                    "Article ID collision detected. "
                    "Please change the title slightly and retry."
                ),
            )
    except HTTPException:
        raise
    except (ValueError, Exception):
        pass  # Collection doesn't exist yet — fine

    # Check semaphore (non-blocking)
    if upload_semaphore.locked():
        raise HTTPException(
            status_code=409,
            detail="Another ingestion is already in progress. Please wait.",
        )

    async with upload_semaphore:
        try:
            start_t = time.perf_counter()

            # Chunk content by markdown headings
            sections = chunk_by_markdown_headings(body.content)

            if not sections:
                raise HTTPException(
                    status_code=422,
                    detail="No content to ingest after processing.",
                )

            # Build chunk stream: (chunk_id, text, metadata)
            now = datetime.now(UTC).isoformat()

            def chunk_stream() -> Iterator[tuple[str, str, dict[str, str]]]:
                for idx, (section_title, chunk_text) in enumerate(sections):
                    chunk_id = f"{article_id}_chunk_{idx}"
                    metadata = {
                        "article_id": article_id,
                        "title": body.title,
                        "section": section_title,
                        "source_type": "manual",
                        "imported_at": now,
                        "tags": ",".join(body.tags),
                    }
                    yield chunk_id, chunk_text, metadata

            # Embed and upsert
            col = await asyncio.to_thread(
                chroma_client.get_or_create_collection,
                KB_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )

            embed_service = request.app.state.sync_embed_service
            pipeline = IngestionPipeline(
                chroma_client=chroma_client,
                embed_fn=embed_service.embed_fn,
            )

            total = await asyncio.to_thread(
                pipeline.upsert_stream, col, chunk_stream(),
            )

            elapsed_ms = int((time.perf_counter() - start_t) * 1000)
            invalidate_article_cache()

            return CreateArticleResponse(
                article_id=article_id,
                title=body.title,
                chunks_ingested=total,
                processing_time_ms=elapsed_ms,
            )

        except HTTPException:
            raise
        except ConnectionError as exc:
            logger.error("Ollama unavailable during article creation: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Embedding service (Ollama) is unavailable.",
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error during article creation")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during article creation.",
            ) from exc


_ARTICLE_ID_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"


@router.put("/articles/{article_id}", response_model=UpdateArticleResponse)
async def update_article(
    request: Request,
    body: UpdateArticleRequest,
    article_id: str = Path(pattern=_ARTICLE_ID_PATTERN),
) -> UpdateArticleResponse:
    """Update title, content, and tags of a manual KB article."""
    chroma_client = request.app.state.chroma_client

    # 1. Verify article exists and is manual
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
        col.get, where={"article_id": article_id}, include=["metadatas"],
    )

    ids: list[str] = result.get("ids", [])
    metadatas: list[dict[str, Any]] = result.get("metadatas", [])

    if not ids:
        raise HTTPException(
            status_code=404,
            detail=f"Article not found: {article_id}",
        )

    first_meta = metadatas[0]
    if first_meta.get("source_type") != "manual":
        raise HTTPException(
            status_code=403,
            detail="Only manual articles can be edited.",
        )

    original_imported_at = first_meta.get("imported_at", "")

    # Check semaphore (non-blocking)
    if upload_semaphore.locked():
        raise HTTPException(
            status_code=409,
            detail="Another ingestion is already in progress. Please wait.",
        )

    async with upload_semaphore:
        try:
            start_t = time.perf_counter()

            # 2. Re-chunk new content
            sections = chunk_by_markdown_headings(body.content)

            if not sections:
                raise HTTPException(
                    status_code=422,
                    detail="No content to ingest after processing.",
                )

            # 3. Build chunk stream preserving original article_id and imported_at
            new_chunk_ids: list[str] = []

            def chunk_stream() -> Iterator[tuple[str, str, dict[str, str]]]:
                for idx, (section_title, chunk_text) in enumerate(sections):
                    chunk_id = f"{article_id}_chunk_{idx}"
                    new_chunk_ids.append(chunk_id)
                    metadata = {
                        "article_id": article_id,
                        "title": body.title,
                        "section": section_title,
                        "source_type": "manual",
                        "imported_at": original_imported_at,
                        "tags": ",".join(body.tags),
                    }
                    yield chunk_id, chunk_text, metadata

            # 4. Upsert new chunks first (safe: old data survives on failure)
            embed_service = request.app.state.sync_embed_service
            pipeline = IngestionPipeline(
                chroma_client=chroma_client,
                embed_fn=embed_service.embed_fn,
            )

            total = await asyncio.to_thread(
                pipeline.upsert_stream, col, chunk_stream(),
            )

            # 5. Delete old chunks that are no longer needed
            stale_ids = [cid for cid in ids if cid not in set(new_chunk_ids)]
            if stale_ids:
                await asyncio.to_thread(col.delete, ids=stale_ids)

            elapsed_ms = int((time.perf_counter() - start_t) * 1000)
            invalidate_article_cache()

            return UpdateArticleResponse(
                article_id=article_id,
                title=body.title,
                chunks_ingested=total,
                processing_time_ms=elapsed_ms,
            )

        except HTTPException:
            raise
        except ConnectionError as exc:
            logger.error("Ollama unavailable during article update: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Embedding service (Ollama) is unavailable.",
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error during article update")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during article update.",
            ) from exc


@router.get("/articles/{article_id}", response_model=ArticleDetailResponse)
async def get_article(
    request: Request,
    article_id: str = Path(pattern=_ARTICLE_ID_PATTERN),
) -> ArticleDetailResponse:
    """Get article detail with all chunks."""
    chroma_client = request.app.state.chroma_client

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
        include=["documents", "metadatas"],
    )

    ids: list[str] = result.get("ids", [])
    documents: list[str] = result.get("documents", [])
    metadatas: list[dict[str, Any]] = result.get("metadatas", [])

    if not ids:
        raise HTTPException(
            status_code=404,
            detail=f"Article not found: {article_id}",
        )

    # Build article metadata from first chunk
    first_meta = metadatas[0]
    source = first_meta.get("source_file") or first_meta.get("source_url") or ""

    # Merge tags from all chunks (union)
    all_tags: set[str] = set()
    for meta in metadatas:
        tags_str = meta.get("tags", "")
        if tags_str:
            all_tags.update(t.strip() for t in tags_str.split(",") if t.strip())

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
        tags=sorted(all_tags),
        chunks=chunks,
    )


@router.patch("/articles/{article_id}/tags", response_model=UpdateTagsResponse)
async def update_tags(
    request: Request,
    body: UpdateTagsRequest,
    article_id: str = Path(pattern=_ARTICLE_ID_PATTERN),
) -> UpdateTagsResponse:
    """Update tags on all chunks of an article."""
    chroma_client = request.app.state.chroma_client
    try:
        col = await asyncio.to_thread(chroma_client.get_collection, KB_COLLECTION)
    except (ValueError, Exception) as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Article not found: {article_id}",
        ) from exc

    result = await asyncio.to_thread(
        col.get, where={"article_id": article_id}, include=["metadatas"],
    )
    ids: list[str] = result.get("ids", [])
    metadatas: list[dict[str, Any]] = result.get("metadatas", [])

    if not ids:
        raise HTTPException(
            status_code=404,
            detail=f"Article not found: {article_id}",
        )

    tags_str = ",".join(body.tags)
    updated_metas = [{**m, "tags": tags_str} for m in metadatas]
    await asyncio.to_thread(col.update, ids=ids, metadatas=updated_metas)
    invalidate_article_cache()

    return UpdateTagsResponse(
        article_id=article_id, tags=body.tags, chunks_updated=len(ids),
    )


@router.get("/tags", response_model=TagListResponse)
async def get_tags(request: Request) -> TagListResponse:
    """Return all unique tags across all articles."""
    index, _ = await _get_article_index(request.app.state.chroma_client)
    all_tags: set[str] = set()
    for article in index.values():
        all_tags.update(article.get("tags", []))
    return TagListResponse(tags=sorted(all_tags))


@router.delete("/articles/{article_id}", response_model=ArticleDeleteResponse)
async def delete_article(
    request: Request,
    article_id: str = Path(pattern=_ARTICLE_ID_PATTERN),
) -> ArticleDeleteResponse:
    """Delete all chunks belonging to an article."""
    chroma_client = request.app.state.chroma_client

    try:
        col = await asyncio.to_thread(
            chroma_client.get_collection, KB_COLLECTION,
        )
    except (ValueError, Exception) as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Article not found: {article_id}",
        ) from exc

    # Get chunk IDs for this article
    result = await asyncio.to_thread(
        col.get, where={"article_id": article_id},
    )

    ids: list[str] = result.get("ids", [])

    if not ids:
        raise HTTPException(
            status_code=404,
            detail=f"Article not found: {article_id}",
        )

    await asyncio.to_thread(col.delete, ids=ids)
    invalidate_article_cache()

    client_ip = request.client.host if request.client else ""
    audit_log(
        "article_delete", client_ip=client_ip,
        detail=f"article_id={article_id} chunks={len(ids)}",
    )

    return ArticleDeleteResponse(
        article_id=article_id,
        chunks_deleted=len(ids),
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(request: Request) -> StatsResponse:
    """Return KB collection statistics."""
    index, total_chunks = await _get_article_index(request.app.state.chroma_client)

    by_source_type: dict[str, int] = {}
    for article in index.values():
        st = article["source_type"]
        by_source_type[st] = by_source_type.get(st, 0) + 1

    return StatsResponse(
        total_articles=len(index),
        total_chunks=total_chunks,
        by_source_type=by_source_type,
    )
