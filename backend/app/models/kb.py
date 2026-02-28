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
    tags: list[str] = []


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
    tags: list[str] = []
    chunks: list[ChunkDetail]


class ArticleDeleteResponse(BaseModel):
    article_id: str
    chunks_deleted: int


class CreateArticleResponse(BaseModel):
    article_id: str
    title: str
    chunks_ingested: int
    processing_time_ms: int


class UpdateArticleResponse(BaseModel):
    article_id: str
    title: str
    chunks_ingested: int
    processing_time_ms: int


class UpdateTagsResponse(BaseModel):
    article_id: str
    tags: list[str]
    chunks_updated: int


class TagListResponse(BaseModel):
    tags: list[str]


class StatsResponse(BaseModel):
    total_articles: int
    total_chunks: int
    by_source_type: dict[str, int]
