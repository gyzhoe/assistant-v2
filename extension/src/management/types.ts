// Re-export shared types that were previously duplicated
export type { IngestUploadResponse, IngestUrlResponse, HealthResponse, ToastMessage } from '@/shared/types'

/** Source type literals */
export type SourceType = 'pdf' | 'html' | 'url' | 'json' | 'csv' | 'manual'

/** Summary of a single KB article (narrows source_type from shared KBArticleListItem) */
export interface ArticleSummary {
  article_id: string
  title: string
  source_type: SourceType
  source: string
  chunk_count: number
  imported_at: string | null
  tags?: string[]
}

/** Full article detail including chunks */
export interface ArticleDetail extends ArticleSummary {
  chunks: ArticleChunk[]
}

/** Single chunk within an article */
export interface ArticleChunk {
  id: string
  text: string
  section: string | null
  metadata: Record<string, unknown>
}

/** Paginated article list response */
export interface ArticleListResponse {
  articles: ArticleSummary[]
  total_articles: number
  page: number
  page_size: number
}

/** KB stats response */
export interface KBStats {
  total_articles: number
  total_chunks: number
  by_source_type: Record<string, number>
}

/** Delete article response */
export interface DeleteResponse {
  article_id: string
  chunks_deleted: number
}

/** Create article response */
export interface CreateArticleResponse {
  article_id: string
  title: string
  chunks_ingested: number
  processing_time_ms: number
}

/** Update tags response */
export interface UpdateTagsResponse {
  article_id: string
  tags: string[]
  chunks_updated: number
}

/** Tag list response */
export interface TagListResponse {
  tags: string[]
}

/** Update article response */
export interface UpdateArticleResponse {
  article_id: string
  title: string
  chunks_ingested: number
  processing_time_ms: number
}

/** Article list query parameters */
export interface ArticleListParams {
  page: number
  page_size: number
  search?: string
  source_type?: SourceType | ''
}
