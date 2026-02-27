"""Pydantic models for KB management endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ArticleSummary(BaseModel):
    article_id: str
    title: str
    source_type: str
    source: str
    chunk_count: int
    imported_at: str | None = None


class ArticleListResponse(BaseModel):
    articles: list[ArticleSummary]
    total_articles: int
    page: int
    page_size: int


class ChunkDetail(BaseModel):
    id: str
    text: str
    section: str | None = None
    metadata: dict[str, object]


class ArticleDetailResponse(BaseModel):
    article_id: str
    title: str
    source_type: str
    source: str
    chunk_count: int
    imported_at: str | None = None
    chunks: list[ChunkDetail]


class ArticleDeleteResponse(BaseModel):
    article_id: str
    chunks_deleted: int


class SourceTypeCount(BaseModel):
    """Count of articles per source type — used as dict values in StatsResponse."""


class StatsResponse(BaseModel):
    total_articles: int
    total_chunks: int
    by_source_type: dict[str, int]
