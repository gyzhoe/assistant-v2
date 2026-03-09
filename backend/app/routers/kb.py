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

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.constants import (
    COSINE_COLLECTION_META,
    KB_COLLECTION,
    LLMModelError,
    parse_tags,
    serialize_tags,
)
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
from app.routers.shared import (
    acquire_ingestion_lock,
    get_client_ip,
)
from app.services.audit import audit_log
from app.services.kb_cache import (
    _get_article_chunks,
    _get_article_index,
    invalidate_article_cache,
)
from app.utils.chunker import chunk_by_markdown_headings
from ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["kb-management"])


# ── Chunk stream helper ──────────────────────────────────────────────────────


def _build_chunk_stream(
    sections: list[tuple[str, str]],
    *,
    article_id: str,
    title: str,
    imported_at: str,
    tags_str: str,
    collect_ids: list[str] | None = None,
) -> Iterator[tuple[str, str, dict[str, str]]]:
    """Yield ``(chunk_id, text, metadata)`` tuples for upsert.

    Shared by :func:`create_article` and :func:`update_article` to avoid
    duplicating chunk-building logic.

    Args:
        sections: list of ``(section_title, chunk_text)`` from the chunker.
        article_id: stable article identifier.
        title: article title stored in every chunk.
        imported_at: ISO timestamp preserved across edits.
        tags_str: comma-separated tags string.
        collect_ids: if provided, each generated chunk id is appended here
            so the caller can track which IDs were created.
    """
    for idx, (section_title, chunk_text) in enumerate(sections):
        chunk_id = f"{article_id}_chunk_{idx}"
        if collect_ids is not None:
            collect_ids.append(chunk_id)
        metadata = {
            "article_id": article_id,
            "title": title,
            "section": section_title,
            "source_type": "manual",
            "imported_at": imported_at,
            "tags": tags_str,
        }
        yield chunk_id, chunk_text, metadata


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

    total_pages = -(-total // page_size)  # ceiling division

    return ArticleListResponse(
        articles=[ArticleSummary(**a) for a in page_articles],
        total_articles=total,
        total_pages=total_pages,
        page=page,
        page_size=page_size,
    )


@router.post("/articles", response_model=CreateArticleResponse, status_code=201)
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

    async with acquire_ingestion_lock():
        try:
            start_t = time.perf_counter()

            # Chunk content by markdown headings
            sections = chunk_by_markdown_headings(body.content)

            if not sections:
                raise HTTPException(
                    status_code=422,
                    detail="No content to ingest after processing.",
                )

            now = datetime.now(UTC).isoformat()
            tags_str = serialize_tags(body.tags)

            # Embed and upsert
            col = await asyncio.to_thread(
                chroma_client.get_or_create_collection,
                KB_COLLECTION,
                metadata=COSINE_COLLECTION_META,
            )

            embed_service = request.app.state.sync_embed_service
            pipeline = IngestionPipeline(
                chroma_client=chroma_client,
                embed_fn=embed_service.embed_fn,
            )

            total = await asyncio.to_thread(
                pipeline.upsert_stream,
                col,
                _build_chunk_stream(
                    sections,
                    article_id=article_id,
                    title=body.title,
                    imported_at=now,
                    tags_str=tags_str,
                ),
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
        except LLMModelError as exc:
            logger.error("LLM model error during article creation: %s", exc)
            raise HTTPException(
                status_code=502,
                detail={"message": str(exc), "error_code": "MODEL_ERROR"},
            ) from exc
        except ConnectionError as exc:
            logger.error("Embed server unavailable during article creation: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Embedding server is unavailable.",
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
    col, ids, metadatas, _ = await _get_article_chunks(
        chroma_client, article_id,
    )

    first_meta = metadatas[0]
    if first_meta.get("source_type") != "manual":
        raise HTTPException(
            status_code=403,
            detail="Only manual articles can be edited.",
        )

    original_imported_at = first_meta.get("imported_at", "")

    async with acquire_ingestion_lock():
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
            tags_str = serialize_tags(body.tags)

            # 4. Upsert new chunks first (safe: old data survives on failure)
            embed_service = request.app.state.sync_embed_service
            pipeline = IngestionPipeline(
                chroma_client=chroma_client,
                embed_fn=embed_service.embed_fn,
            )

            total = await asyncio.to_thread(
                pipeline.upsert_stream,
                col,
                _build_chunk_stream(
                    sections,
                    article_id=article_id,
                    title=body.title,
                    imported_at=original_imported_at,
                    tags_str=tags_str,
                    collect_ids=new_chunk_ids,
                ),
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
        except LLMModelError as exc:
            logger.error("LLM model error during article update: %s", exc)
            raise HTTPException(
                status_code=502,
                detail={"message": str(exc), "error_code": "MODEL_ERROR"},
            ) from exc
        except ConnectionError as exc:
            logger.error("Embed server unavailable during article update: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Embedding server is unavailable.",
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

    col, ids, metadatas, result = await _get_article_chunks(
        chroma_client, article_id, include=["documents", "metadatas"],
    )
    documents: list[str] = result.get("documents", [])

    # Build article metadata from first chunk
    first_meta = metadatas[0]
    source = first_meta.get("source_file") or first_meta.get("source_url") or ""

    # Merge tags from all chunks (union)
    all_tags: set[str] = set()
    for meta in metadatas:
        all_tags.update(parse_tags(meta.get("tags", "")))

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

    col, ids, metadatas, _ = await _get_article_chunks(
        chroma_client, article_id,
    )

    tags_str = serialize_tags(body.tags)
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

    col, ids, _, _result = await _get_article_chunks(chroma_client, article_id)

    await asyncio.to_thread(col.delete, ids=ids)
    invalidate_article_cache()

    audit_log(
        "article_delete", client_ip=get_client_ip(request),
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
