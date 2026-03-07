# API Contract — AI Helpdesk Assistant Backend

Base URL: `http://localhost:8765`

## Table of Contents

1. [Authentication](#authentication)
2. [Rate Limiting](#rate-limiting)
3. [Request Size Limits](#request-size-limits)
4. [Security Headers](#security-headers)
5. [Health / Status Endpoints](#1-health--status-endpoints)
6. [Generation Endpoints](#2-generation-endpoints)
7. [Knowledge Base CRUD Endpoints](#3-knowledge-base-crud-endpoints)
8. [Knowledge Base Import / Ingestion Endpoints](#4-knowledge-base-import--ingestion-endpoints)
9. [Search / Tag Endpoints](#5-search--tag-endpoints)
10. [Feedback Endpoints](#6-feedback-endpoints)
11. [Settings / Config Endpoints](#7-settings--config-endpoints)
12. [Model Download Endpoints](#8-model-download-endpoints)
13. [Chrome Runtime Message Types](#chrome-runtime-message-types)

---

## Authentication

The backend supports optional API token authentication via the `X-Extension-Token` header.

| Setting | Description |
|---|---|
| `API_TOKEN` env var | Shared secret. Leave empty (`""`) in dev to disable auth. |
| Header name | `X-Extension-Token` |
| Exempt paths | `/health`, `/docs`, `/openapi.json` |

When `API_TOKEN` is set, all requests (except exempt paths) must include the token.
Missing or invalid tokens return `401 Unauthorized`:

```json
{
  "detail": "Unauthorized. Missing or invalid X-Extension-Token header."
}
```

Some destructive endpoints (`/shutdown`, `/llm/start`, `/llm/stop`) additionally enforce token auth via a per-route dependency, even if the global middleware would allow them.

---

## Rate Limiting

In-process rate limiter applied per client IP. Only specific paths are rate-limited.

| Path | Max requests per minute |
|---|---|
| `/generate` | 20 (configurable via `RATE_LIMIT_PER_MINUTE`) |
| `/ingest/upload` | 5 |
| `/ingest/url` | 5 |
| `/feedback` | 10 |

When exceeded, the response is `429 Too Many Requests`:

```json
{
  "detail": "Rate limit exceeded. Max 20 requests per minute.",
  "error_code": "RATE_LIMITED"
}
```

---

## Request Size Limits

Requests exceeding `MAX_REQUEST_BYTES` (default 64 KB) are rejected with `413 Payload Too Large`.

**Exempt paths** (these have their own size handling): `/ingest/upload`, `/ingest/url`, `/kb/articles`.

```json
{
  "detail": "Request body too large. Max 65536 bytes.",
  "error_code": "PAYLOAD_TOO_LARGE"
}
```

---

## Security Headers

All responses include the following headers:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Cache-Control` | `no-store` |
| `Referrer-Policy` | `no-referrer` |

The `Server` header is stripped from all responses.

---

## 1. Health / Status Endpoints

### `GET /health`

Returns the current status of all backend dependencies.

**Authentication:** Not required (exempt from token auth).

**Rate limit:** None.

#### Response `200 OK`

```json
{
  "status": "ok",
  "llm_reachable": true,
  "chroma_ready": true,
  "chroma_doc_counts": {
    "whd_tickets": 1432,
    "kb_articles": 87
  },
  "version": "1.8.0"
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `status` | `"ok" \| "degraded"` | `"ok"` when both llama-server and ChromaDB are healthy |
| `llm_reachable` | boolean | Whether llama-server responds at `/health` |
| `chroma_ready` | boolean | Whether ChromaDB is initialized |
| `chroma_doc_counts` | object | Document counts per collection (key = collection name) |
| `version` | string | Backend version from config |

---

### `POST /shutdown`

Gracefully shuts down the backend server after a 0.5-second delay.

**Authentication:** Required (`X-Extension-Token` header, enforced even in dev mode when `API_TOKEN` is set).

**Rate limit:** None.

#### Response `200 OK`

```json
{
  "status": "shutting_down"
}
```

#### Error responses

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing or invalid token |

---

### `POST /llm/start`

Starts the llama-server process(es) as detached background processes. Returns immediately without waiting for llama-server to be fully ready.

**Authentication:** Required (`X-Extension-Token` header).

**Rate limit:** None.

#### Response `200 OK` — already running

```json
{
  "status": "already_running"
}
```

#### Response `200 OK` — starting

```json
{
  "status": "starting"
}
```

#### Error responses

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing or invalid token |

---

### `POST /llm/stop`

Stops the llama-server process(es) (uses `taskkill` on Windows, `pkill` on other platforms).

**Authentication:** Required (`X-Extension-Token` header).

**Rate limit:** None.

#### Response `200 OK`

```json
{
  "status": "stopping"
}
```

#### Error responses

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing or invalid token |

---

## 2. Generation Endpoints

### `POST /generate`

Retrieves RAG context (ChromaDB + optional Microsoft Learn search) and generates a helpdesk reply using the local LLM.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** 20 requests per minute per IP (configurable).

#### Request Body

```json
{
  "ticket_subject": "Cannot access network drive after password reset",
  "ticket_description": "User reports they cannot access the shared network drive...",
  "requester_name": "Alex Johnson",
  "category": "Network",
  "status": "Open",
  "model": "qwen3.5:9b",
  "max_context_docs": 5,
  "stream": false,
  "include_web_context": true,
  "prompt_suffix": "",
  "custom_fields": {},
  "pinned_article_ids": []
}
```

#### Request fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `ticket_subject` | string | no | `""` | Ticket subject line (max 500 chars) |
| `ticket_description` | string | no | `""` | Full problem description (max 16,000 chars) |
| `requester_name` | string | no | `""` | Requester's name (max 200 chars) |
| `category` | string | no | `""` | Ticket category (max 200 chars) |
| `status` | string | no | `""` | Ticket status (max 200 chars) |
| `model` | string | no | `"qwen3.5:9b"` | GGUF model to use (max 100 chars) |
| `max_context_docs` | integer | no | `5` | Max RAG documents to include (1-20) |
| `stream` | boolean | no | `false` | Reserved for future streaming support |
| `include_web_context` | boolean | no | `true` | Include Microsoft Learn search results as additional context |
| `prompt_suffix` | string | no | `""` | Custom instructions appended to the prompt (max 2,000 chars) |
| `custom_fields` | object | no | `{}` | Key-value pairs for custom ticket fields. Max 10 keys; key max 100 chars; value max 500 chars. Control characters are stripped. |
| `pinned_article_ids` | string[] | no | `[]` | KB article IDs to always include as context (max 10 items, each max 200 chars) |

#### Response `200 OK`

```json
{
  "reply": "Hi Alex,\n\n1. Press Windows+R, type...",
  "model_used": "qwen3.5:9b",
  "context_docs": [
    {
      "content": "When a user cannot access a network drive after a password reset...",
      "source": "kb",
      "score": 0.87,
      "metadata": {
        "article_id": "KB-042",
        "title": "Network Drive Access After Password Reset"
      }
    }
  ],
  "latency_ms": 2340
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `reply` | string | Generated helpdesk reply text |
| `model_used` | string | Model that produced the reply |
| `context_docs` | ContextDoc[] | RAG documents used as context (see below) |
| `latency_ms` | integer | Total processing time in milliseconds |

**ContextDoc schema:**

| Field | Type | Description |
|---|---|---|
| `content` | string | Document text |
| `source` | string | `"kb"` or `"ticket"` |
| `score` | float | Similarity score (0.0 - 1.0) |
| `metadata` | object | Source-specific metadata (article_id, title, etc.) |

#### Error responses

| Status | Condition | Body |
|---|---|---|
| `401 Unauthorized` | Missing/invalid token | `{"detail": "Unauthorized..."}` |
| `422 Unprocessable Entity` | Validation error | Pydantic validation detail array |
| `429 Too Many Requests` | Rate limit exceeded | `{"detail": "Rate limit exceeded...", "error_code": "RATE_LIMITED"}` |
| `503 Service Unavailable` | LLM server unreachable | `{"detail": {"message": "...", "error_code": "LLM_DOWN"}}` |

---

## 3. Knowledge Base CRUD Endpoints

All KB endpoints use the `/kb` prefix.

### `GET /kb/articles`

List KB articles with pagination, search, and source type filtering.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None.

#### Query parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `page` | integer | no | `1` | Page number |
| `page_size` | integer | no | `20` | Articles per page |
| `search` | string | no | `null` | Case-insensitive title search |
| `source_type` | string | no | `null` | Filter by source type (e.g., `"html"`, `"pdf"`, `"manual"`, `"url"`) |

#### Response `200 OK`

```json
{
  "articles": [
    {
      "article_id": "a1b2c3d4e5f67890",
      "title": "VPN Troubleshooting Guide",
      "source_type": "pdf",
      "source": "vpn-guide.pdf",
      "chunk_count": 12,
      "imported_at": "2025-03-15T10:30:00+00:00",
      "tags": ["networking", "vpn"]
    }
  ],
  "total_articles": 42,
  "page": 1,
  "page_size": 20
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `articles` | ArticleSummary[] | Page of article summaries (see below) |
| `total_articles` | integer | Total articles matching the filter |
| `page` | integer | Current page number |
| `page_size` | integer | Page size used |

**ArticleSummary schema:**

| Field | Type | Description |
|---|---|---|
| `article_id` | string | Unique article identifier (16-char hex hash) |
| `title` | string | Article title |
| `source_type` | string | How the article was imported: `"html"`, `"pdf"`, `"json"`, `"csv"`, `"url"`, `"manual"` |
| `source` | string | Source filename or URL |
| `chunk_count` | integer | Number of text chunks stored |
| `imported_at` | string \| null | ISO 8601 timestamp of import |
| `tags` | string[] | Article tags |

---

### `POST /kb/articles`

Create a new KB article from markdown content. The article is chunked by markdown headings, embedded, and stored in ChromaDB.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None (but subject to ingestion semaphore — one ingestion at a time).

#### Request Body

```json
{
  "title": "Password Reset Procedure",
  "content": "# Overview\n\nThis guide covers the standard password reset...",
  "tags": ["security", "passwords"]
}
```

#### Request fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | string | yes | — | Article title (1-200 chars) |
| `content` | string | yes | — | Markdown content (1-100,000 chars) |
| `tags` | string[] | no | `[]` | Tags (max 20 tags, each max 100 chars, no commas) |

#### Response `200 OK`

```json
{
  "article_id": "a1b2c3d4e5f67890",
  "title": "Password Reset Procedure",
  "chunks_ingested": 5,
  "processing_time_ms": 1200
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `article_id` | string | Generated article ID (truncated SHA-256 hash of title) |
| `title` | string | Article title |
| `chunks_ingested` | integer | Number of chunks stored |
| `processing_time_ms` | integer | Total processing time |

#### Error responses

| Status | Condition |
|---|---|
| `409 Conflict` | Duplicate title or article ID collision |
| `409 Conflict` | Another ingestion is already in progress |
| `422 Unprocessable Entity` | Validation error (empty title/content, invalid tags) |
| `422 Unprocessable Entity` | No content to ingest after processing |
| `500 Internal Server Error` | Unexpected error during creation |
| `503 Service Unavailable` | LLM server unreachable for embedding |

---

### `GET /kb/articles/{article_id}`

Get full article detail including all chunks.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None.

#### Path parameters

| Parameter | Type | Description |
|---|---|---|
| `article_id` | string | Article identifier |

#### Response `200 OK`

```json
{
  "article_id": "a1b2c3d4e5f67890",
  "title": "VPN Troubleshooting Guide",
  "source_type": "pdf",
  "source": "vpn-guide.pdf",
  "chunk_count": 12,
  "imported_at": "2025-03-15T10:30:00+00:00",
  "tags": ["networking", "vpn"],
  "chunks": [
    {
      "id": "a1b2c3d4e5f67890_chunk_0",
      "text": "This guide covers common VPN connectivity issues...",
      "section": "Overview",
      "metadata": {
        "article_id": "a1b2c3d4e5f67890",
        "title": "VPN Troubleshooting Guide",
        "section": "Overview",
        "source_type": "pdf",
        "imported_at": "2025-03-15T10:30:00+00:00",
        "tags": "networking,vpn"
      }
    }
  ]
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `article_id` | string | Article identifier |
| `title` | string | Article title |
| `source_type` | string | Import source type |
| `source` | string | Source filename or URL |
| `chunk_count` | integer | Number of chunks |
| `imported_at` | string \| null | ISO 8601 timestamp |
| `tags` | string[] | Union of tags from all chunks |
| `chunks` | ChunkDetail[] | All chunks for this article |

**ChunkDetail schema:**

| Field | Type | Description |
|---|---|---|
| `id` | string | Chunk ID (format: `{article_id}_chunk_{index}`) |
| `text` | string | Chunk text content |
| `section` | string \| null | Section heading (if chunked by heading) |
| `metadata` | object | Full ChromaDB metadata for the chunk |

#### Error responses

| Status | Condition |
|---|---|
| `404 Not Found` | Article does not exist |

---

### `PUT /kb/articles/{article_id}`

Update the title, content, and tags of a manual KB article. The article is re-chunked and re-embedded. Old chunks that are no longer needed are deleted atomically (new chunks are upserted before old chunks are removed).

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None (but subject to ingestion semaphore).

#### Path parameters

| Parameter | Type | Description |
|---|---|---|
| `article_id` | string | Article identifier |

#### Request Body

```json
{
  "title": "Updated Password Reset Procedure",
  "content": "# Overview\n\nRevised procedure for password reset...",
  "tags": ["security", "passwords", "updated"]
}
```

#### Request fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | string | yes | — | Article title (1-200 chars) |
| `content` | string | yes | — | Markdown content (1-100,000 chars) |
| `tags` | string[] | no | `[]` | Tags (max 20, each max 100 chars, no commas) |

#### Response `200 OK`

```json
{
  "article_id": "a1b2c3d4e5f67890",
  "title": "Updated Password Reset Procedure",
  "chunks_ingested": 6,
  "processing_time_ms": 1500
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `article_id` | string | Article identifier |
| `title` | string | Updated title |
| `chunks_ingested` | integer | New chunk count |
| `processing_time_ms` | integer | Total processing time |

#### Error responses

| Status | Condition |
|---|---|
| `403 Forbidden` | Article is not a manual article (only manual articles can be edited) |
| `404 Not Found` | Article does not exist |
| `409 Conflict` | Another ingestion is already in progress |
| `422 Unprocessable Entity` | Validation error or no content after processing |
| `500 Internal Server Error` | Unexpected error |
| `503 Service Unavailable` | LLM server unreachable for embedding |

---

### `PATCH /kb/articles/{article_id}/tags`

Update tags on all chunks of an article. This is a lightweight operation that does not re-embed — it only updates the `tags` metadata field on existing chunks.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None.

#### Path parameters

| Parameter | Type | Description |
|---|---|---|
| `article_id` | string | Article identifier |

#### Request Body

```json
{
  "tags": ["networking", "vpn", "troubleshooting"]
}
```

#### Request fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `tags` | string[] | no | `[]` | New tags to replace existing tags (max 20, each max 100 chars, no commas) |

#### Response `200 OK`

```json
{
  "article_id": "a1b2c3d4e5f67890",
  "tags": ["networking", "troubleshooting", "vpn"],
  "chunks_updated": 12
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `article_id` | string | Article identifier |
| `tags` | string[] | Updated tags |
| `chunks_updated` | integer | Number of chunks that were updated |

#### Error responses

| Status | Condition |
|---|---|
| `404 Not Found` | Article does not exist |
| `422 Unprocessable Entity` | Invalid tags (commas, too many, too long) |

---

### `DELETE /kb/articles/{article_id}`

Delete all chunks belonging to an article from ChromaDB.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None.

#### Path parameters

| Parameter | Type | Description |
|---|---|---|
| `article_id` | string | Article identifier |

#### Response `200 OK`

```json
{
  "article_id": "a1b2c3d4e5f67890",
  "chunks_deleted": 12
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `article_id` | string | Deleted article's identifier |
| `chunks_deleted` | integer | Number of chunks removed |

#### Error responses

| Status | Condition |
|---|---|
| `404 Not Found` | Article does not exist |

---

## 4. Knowledge Base Import / Ingestion Endpoints

All ingestion operations are serialized — only one upload or URL ingestion can run at a time (shared semaphore). Concurrent attempts return `409 Conflict`.

### `POST /ingest/upload`

Upload a single file for ingestion into ChromaDB. Accepts `multipart/form-data`.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** 5 requests per minute per IP.

#### Request

- **Content-Type:** `multipart/form-data`
- **Field:** `file` — the file to ingest
- **Supported extensions:** `.json`, `.csv`, `.html`, `.htm`, `.pdf`
- **Max file size:** 50 MB (configurable via `MAX_UPLOAD_BYTES`)

#### Response `200 OK`

```json
{
  "filename": "kb-article.pdf",
  "collection": "kb_articles",
  "chunks_ingested": 42,
  "processing_time_ms": 12340,
  "warning": null
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `filename` | string | Sanitized filename (directory components stripped) |
| `collection` | string | Target ChromaDB collection (`whd_tickets` or `kb_articles`) |
| `chunks_ingested` | integer | Number of text chunks stored |
| `processing_time_ms` | integer | Total processing time |
| `warning` | string \| null | Warning message (e.g., zero chunks extracted from images-only PDF) |

#### Error responses

| Status | Condition |
|---|---|
| `409 Conflict` | Another upload/ingestion is already in progress |
| `413 Payload Too Large` | File exceeds `MAX_UPLOAD_BYTES` (50 MB default) |
| `422 Unprocessable Entity` | Unsupported extension, no filename, empty file, or corrupt content |
| `500 Internal Server Error` | Unexpected error during ingestion |
| `503 Service Unavailable` | LLM server unreachable for embedding |

---

### `POST /ingest/url`

Fetch a URL server-side, extract text content, chunk it, and ingest into ChromaDB (`kb_articles` collection). Shares the ingestion semaphore with file upload.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** 5 requests per minute per IP.

#### Request Body

```json
{
  "url": "https://learn.microsoft.com/en-us/windows-server/networking/802-1x"
}
```

#### Request fields

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string (URL) | yes | The URL to fetch and ingest (http/https only) |

#### Response `200 OK`

```json
{
  "url": "https://learn.microsoft.com/en-us/windows-server/networking/802-1x",
  "collection": "kb_articles",
  "chunks_ingested": 12,
  "processing_time_ms": 3200,
  "title": "Configure 802.1X wired access",
  "warning": null
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `url` | string | The URL that was fetched |
| `collection` | string | Target ChromaDB collection (always `kb_articles`) |
| `chunks_ingested` | integer | Number of text chunks stored |
| `processing_time_ms` | integer | Total processing time |
| `title` | string \| null | Page title extracted from HTML |
| `warning` | string \| null | Warning message (e.g., no content extracted) |

#### Error responses

| Status | Condition |
|---|---|
| `409 Conflict` | Another ingestion is already in progress |
| `413 Payload Too Large` | Response exceeds 5 MB |
| `422 Unprocessable Entity` | SSRF violation, unsupported Content-Type, invalid URL, or fetch failure |
| `500 Internal Server Error` | Unexpected error during URL ingestion |
| `503 Service Unavailable` | LLM server unreachable for embedding |

#### SSRF prevention

URLs are validated before fetching:
- Scheme must be `http` or `https`
- Hostname is resolved via DNS and checked against private IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16`, `::1`, `fe80::/10`)
- IPv4-mapped IPv6 addresses (e.g., `::ffff:127.0.0.1`) are detected and blocked
- Redirects are followed manually (max 10 hops), with SSRF re-validation on every hop
- Content-Type must be `text/html`, `text/plain`, or `application/xhtml+xml`

---

### `POST /ingest/collections/{name}/clear`

Clear all documents from a ChromaDB collection. Idempotent — clearing a non-existent collection succeeds silently.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None.

#### Path parameters

| Parameter | Type | Description |
|---|---|---|
| `name` | string | Collection name: `whd_tickets` or `kb_articles` |

#### Response `200 OK`

```json
{
  "status": "ok",
  "collection": "kb_articles"
}
```

#### Error responses

| Status | Condition | Body |
|---|---|---|
| `422 Unprocessable Entity` | Invalid collection name | `{"detail": "Unknown collection: foo. Allowed: kb_articles, whd_tickets"}` |

---

## 5. Search / Tag Endpoints

### `GET /kb/tags`

Return all unique tags across all KB articles.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None.

#### Response `200 OK`

```json
{
  "tags": ["active-directory", "networking", "passwords", "vpn"]
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `tags` | string[] | Sorted list of all unique tags |

---

### `GET /kb/stats`

Return KB collection statistics.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None.

#### Response `200 OK`

```json
{
  "total_articles": 42,
  "total_chunks": 387,
  "by_source_type": {
    "pdf": 15,
    "html": 20,
    "manual": 5,
    "url": 2
  }
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `total_articles` | integer | Total number of unique articles |
| `total_chunks` | integer | Total chunks across all articles |
| `by_source_type` | object | Article count per source type (key = source type, value = count) |

---

## 6. Feedback Endpoints

### `POST /feedback`

Store a user's rating (good/bad) for a generated reply. Rated replies are embedded and stored in a separate `rated_replies` ChromaDB collection, enabling dynamic few-shot prompting for future generations.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** 10 requests per minute per IP.

#### Request Body

```json
{
  "ticket_subject": "Cannot access network drive",
  "ticket_description": "User reports they cannot access the shared drive...",
  "category": "Network",
  "reply": "Hi Alex,\n\n1. Open Credential Manager...",
  "rating": "good"
}
```

#### Request fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `ticket_subject` | string | yes | — | Original ticket subject (max 500 chars) |
| `ticket_description` | string | yes | — | Original ticket description (max 16,000 chars) |
| `category` | string | no | `""` | Ticket category (max 200 chars) |
| `reply` | string | yes | — | The generated reply text (max 4,000 chars) |
| `rating` | string | yes | — | `"good"` or `"bad"` |

#### Response `204 No Content`

Empty body on success.

#### Error responses

| Status | Condition |
|---|---|
| `422 Unprocessable Entity` | Validation error (missing required field, invalid rating value) |
| `503 Service Unavailable` | LLM server/ChromaDB unavailable for embedding |

---

## 7. Settings / Config Endpoints

### `GET /models`

List available GGUF models by scanning the `models/` directory.

**Authentication:** Required when `API_TOKEN` is configured.

**Rate limit:** None.

#### Response `200 OK`

```json
{
  "models": ["qwen3.5:9b", "llama3.2:3b"],
  "current": "qwen3.5:9b"
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `models` | string[] | List of available GGUF model names |
| `current` | string | Currently loaded model name |

#### Error responses

| Status | Condition | Body |
|---|---|---|
| `503 Service Unavailable` | Cannot scan models directory | `{"detail": {"message": "Cannot list models.", "error_code": "LLM_DOWN"}}` |

---

### `POST /llm/switch`

Switch the currently loaded GGUF model. Stops the running llama-server chat instance and restarts it with the specified model.

**Authentication:** Required (`X-Extension-Token` header).

**Rate limit:** None.

#### Request Body

```json
{
  "model": "llama3.2:3b"
}
```

#### Request fields

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | string | yes | Name of the GGUF model to load |

#### Response `200 OK`

```json
{
  "status": "switching",
  "model": "llama3.2:3b"
}
```

#### Error responses

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing or invalid token |
| `404 Not Found` | Model GGUF file not found in models directory |

---

## 8. Model Download Endpoints

### `POST /models/download`

Start a background download of one or all GGUF models from HuggingFace.

**Authentication:** Required (`X-Extension-Token` header).

**Rate limit:** None.

#### Request Body

```json
{
  "models": ["Qwen3.5-9B-Q4_K_M.gguf"]
}
```

#### Request fields

| Field | Type | Required | Description |
|---|---|---|---|
| `models` | string[] | no | List of GGUF filenames to download. Empty list downloads all missing non-embed models. |

#### Response `200 OK`

```json
{
  "status": "started",
  "models": ["Qwen3.5-9B-Q4_K_M.gguf"]
}
```

#### Error responses

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing or invalid token |
| `409 Conflict` | A download is already in progress (`{"status": "already_downloading"}`) |

---

### `GET /models/download/status`

Poll the progress of an active model download.

**Authentication:** Required (`X-Extension-Token` header).

**Rate limit:** None.

#### Response `200 OK`

```json
{
  "downloading": true,
  "current_model": "Qwen3.5-9B-Q4_K_M.gguf",
  "bytes_downloaded": 1800000000,
  "bytes_total": 4300000000,
  "models_completed": 0,
  "models_total": 1,
  "error": ""
}
```

#### Response fields

| Field | Type | Description |
|---|---|---|
| `downloading` | boolean | Whether a download is currently active |
| `current_model` | string | GGUF filename being downloaded (empty when idle) |
| `bytes_downloaded` | integer | Bytes downloaded for the current file |
| `bytes_total` | integer | Total size of the current file in bytes |
| `models_completed` | integer | Number of models finished so far |
| `models_total` | integer | Total number of models in this download batch |
| `error` | string | Error message if the download failed (empty on success) |

---

### `POST /models/download/cancel`

Cancel an in-flight model download.

**Authentication:** Required (`X-Extension-Token` header).

**Rate limit:** None.

#### Response `200 OK`

```json
{
  "status": "cancelling"
}
```

#### Error responses

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing or invalid token |

Returns `{"status": "not_downloading"}` if no download is active (not an error, HTTP 200).

---

### Static: `/manage/*`

The backend serves a static KB management SPA from `static/manage/` when the directory exists. This is an HTML SPA served with `StaticFiles(html=True)`, not an API endpoint.

**Authentication:** Not subject to API token middleware (static file serving).

**Note:** This mount is registered after all API routes, so `/kb/*` API endpoints take priority.

---

## Deployment Notes

### Rate Limiting

The backend applies per-client IP rate limits using the direct TCP connection address.

**Default (local-only) deployment:** This works correctly because all traffic
originates from `localhost` and there is only one client.

**Behind a reverse proxy:** All requests appear to come from the proxy's IP, so
every user shares the same rate-limit bucket. To restore per-client limiting in a
proxied deployment, either:

1. Launch uvicorn with `--proxy-headers --forwarded-allow-ips <proxy-ip>` so that
   `X-Forwarded-For` is trusted and the real client IP is used.
2. Move rate limiting to the proxy layer (e.g., nginx `limit_req_zone`) and rely on
   the proxy to enforce limits before requests reach the application.

### /manage SPA Authentication

The `/manage` static mount (KB management UI) is served without authentication.
This is acceptable for the default local-only deployment where network access is
restricted to the local machine. For network-exposed deployments, serve `/manage`
behind an authenticated reverse proxy or add authentication middleware.

---

## Chrome Runtime Message Types

Defined in `extension/src/shared/messages.ts`.

### Content Script → Background → Sidebar

```typescript
type ContentToSidebarMessage =
  | { type: 'TICKET_DATA_UPDATED'; payload: TicketData }
  | { type: 'INSERT_SUCCESS' }
  | { type: 'INSERT_FAILED'; payload: { reason: string } }
  | { type: 'NOT_A_TICKET_PAGE' }
```

### Sidebar → Background → Content Script

```typescript
type SidebarToContentMessage =
  | { type: 'INSERT_REPLY'; payload: { text: string } }
  | { type: 'REQUEST_TICKET_DATA' }
```

### `TicketData` type

```typescript
interface TicketData {
  subject: string
  description: string
  requesterName: string
  category: string
  status: string
  ticketUrl: string
}
```
