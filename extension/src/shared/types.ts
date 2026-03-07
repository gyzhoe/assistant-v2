/** A single note from the WHD ticket Notes section */
export interface NoteData {
  author: string
  text: string
  type: 'client' | 'tech_visible' | 'tech_internal'
  date: string
  noteId: string
  timeSpent: string
}

/** Ticket data extracted from the WHD DOM */
export interface TicketData {
  subject: string
  description: string
  requesterName: string
  category: string
  status: string
  ticketUrl: string
  customFields: Record<string, string>
  notes: NoteData[]
}

/** Settings persisted to chrome.storage.sync */
export interface AppSettings {
  backendUrl: string
  defaultModel: string
  availableModels: string[]
  selectorOverrides: Partial<SelectorConfig>
  promptSuffix: string
  theme: 'light' | 'dark' | 'system'
  autoInsert: boolean
  insertTargetSelector: string
}

/**
 * Security credentials stored in chrome.storage.local (device-only, never synced).
 * The apiToken must match the API_TOKEN env var set on the backend server.
 */
export interface LocalSecrets {
  apiToken: string
}

/** CSS selector config for WHD DOM fields */
export interface SelectorConfig {
  subject: string
  description: string
  requesterName: string
  category: string
  status: string
  techNotes: string
}

/** A pinned KB article for additional context */
export interface KBArticlePin {
  article_id: string
  title: string
}

/** Generate API request */
export interface GenerateRequest {
  ticket_subject: string
  ticket_description: string
  requester_name: string
  category: string
  status: string
  model: string
  max_context_docs: number
  stream: boolean
  include_web_context: boolean
  prompt_suffix: string
  custom_fields: Record<string, string>
  pinned_article_ids?: string[]
  notes?: Array<{
    author: string
    text: string
    type: 'client' | 'tech_visible' | 'tech_internal'
    date: string
    note_id: string
    time_spent: string
  }>
}

/** Single retrieved context document */
export interface ContextDoc {
  content: string
  source: string
  score: number
  metadata: Record<string, unknown>
}

/** Generate API response */
export interface GenerateResponse {
  reply: string
  model_used: string
  context_docs: ContextDoc[]
  latency_ms: number
}

/** Health check response */
export interface HealthResponse {
  status: 'ok' | 'degraded'
  llm_reachable: boolean
  chroma_ready: boolean
  chroma_doc_counts: Record<string, number>
  version: string
}

/** Ingest upload response */
export interface IngestUploadResponse {
  filename: string
  collection: string
  chunks_ingested: number
  processing_time_ms: number
  warning: string | null
}

/** Feedback (reply rating) request */
export interface FeedbackRequest {
  ticket_subject: string
  ticket_description: string
  category: string
  reply: string
  rating: 'good' | 'bad'
}

/** Feedback (reply rating) response — returned by POST /feedback */
export interface FeedbackResponse {
  id: string
}

/** Ingest URL response */
export interface IngestUrlResponse {
  url: string
  collection: string
  chunks_ingested: number
  processing_time_ms: number
  title: string | null
  warning: string | null
}

/** KB article summary (from GET /kb/articles) */
export interface KBArticleListItem {
  article_id: string
  title: string
  source_type: string
  source: string
  chunk_count: number
  imported_at: string | null
  tags?: string[]
}

/** Toast notification */
export interface ToastMessage {
  id: string
  text: string
  type: 'success' | 'error' | 'info'
  /** When true, the toast does not auto-dismiss — user must close it manually. */
  persistent?: boolean
  action?: {
    label: string
    onClick: () => void
  }
}

/** Per-model metadata from GET /models */
export interface ModelInfo {
  downloaded: boolean
  size_bytes: number | null
  description: string
  gguf_name: string
}

/** Model download progress from GET /models/download/status */
export interface ModelDownloadStatus {
  downloading: boolean
  current_model: string | null
  bytes_downloaded: number
  bytes_total: number
  models_completed: number
  models_total: number
  error: string
}

/** Models endpoint response */
export interface ModelsResponse {
  models: string[]
  current: string
  model_info: Record<string, ModelInfo>
}

/** KB article list response */
export interface KBArticleListResponse {
  articles: KBArticleListItem[]
  total_articles: number
  page: number
  page_size: number
}
