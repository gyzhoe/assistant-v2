# API Contract — AI Helpdesk Assistant Backend

Base URL: `http://localhost:8765`

---

## `GET /health`

Returns the current status of all backend dependencies.

### Response `200 OK`
```json
{
  "status": "ok",
  "ollama_reachable": true,
  "chroma_ready": true,
  "chroma_doc_counts": {
    "whd_tickets": 1432,
    "kb_articles": 87
  },
  "version": "1.0.0"
}
```

### Response fields
| Field | Type | Description |
|---|---|---|
| `status` | `"ok" \| "degraded"` | Overall status |
| `ollama_reachable` | boolean | Whether Ollama is responding |
| `chroma_ready` | boolean | Whether ChromaDB is initialized |
| `chroma_doc_counts` | object | Document counts per collection |
| `version` | string | Backend version |

---

## `POST /generate`

Retrieves RAG context and generates a reply using the local LLM.

### Request Body
```json
{
  "ticket_subject": "Cannot access network drive after password reset",
  "ticket_description": "User Alex Johnson reports she cannot access the \\\\fileserver\\shared drive...",
  "requester_name": "Alex Johnson",
  "category": "Network",
  "status": "Open",
  "model": "llama3.2:3b",
  "max_context_docs": 5,
  "stream": false,
  "include_web_context": true,
  "prompt_suffix": "",
  "custom_fields": {}
}
```

### Request fields
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `ticket_subject` | string | yes | — | Ticket subject line |
| `ticket_description` | string | yes | — | Full problem description |
| `requester_name` | string | no | `""` | Requester's name |
| `category` | string | no | `""` | WHD ticket category |
| `status` | string | no | `""` | WHD ticket status |
| `model` | string | no | `"llama3.2:3b"` | Ollama model to use |
| `max_context_docs` | integer | no | `5` | Max RAG documents to include |
| `stream` | boolean | no | `false` | Streaming not yet implemented |
| `include_web_context` | boolean | no | `true` | Include Microsoft Learn search results as additional context |
| `prompt_suffix` | string | no | `""` | Custom instructions appended to the prompt (max 2000 chars) |
| `custom_fields` | object | no | `{}` | WHD custom fields (e.g., building, room, MAC address) |

### Response `200 OK`
```json
{
  "reply": "Hi Alex,\n\nThank you for reaching out...",
  "model_used": "llama3.2:3b",
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

### Response `503 Service Unavailable` — Ollama down
```json
{
  "detail": "Ollama service unreachable at http://localhost:11434",
  "error_code": "OLLAMA_DOWN"
}
```

### Response `422 Unprocessable Entity` — Validation error
```json
{
  "detail": [
    {
      "loc": ["body", "ticket_subject"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## `GET /models`

Lists available Ollama models (proxies Ollama's `/api/tags`).

### Response `200 OK`
```json
{
  "models": ["llama3.2:3b", "llama3.1:8b", "mistral:7b"]
}
```

---

## `POST /ingest/upload`

Uploads a single file for ingestion into ChromaDB. Accepts multipart/form-data.

### Request
- Content-Type: `multipart/form-data`
- Field: `file` — the file to ingest
- Supported extensions: `.json`, `.csv`, `.html`, `.htm`, `.pdf`
- Max file size: 50 MB (configurable via `MAX_UPLOAD_BYTES`)

### Response `200 OK`
```json
{
  "filename": "kb-article.pdf",
  "collection": "kb_articles",
  "chunks_ingested": 42,
  "processing_time_ms": 12340,
  "warning": null
}
```

### Response fields
| Field | Type | Description |
|---|---|---|
| `filename` | string | Sanitized filename |
| `collection` | string | Target ChromaDB collection (`whd_tickets` or `kb_articles`) |
| `chunks_ingested` | integer | Number of text chunks stored |
| `processing_time_ms` | integer | Total processing time |
| `warning` | string \| null | Warning message (e.g., zero chunks extracted) |

### Error responses
| Status | Condition |
|---|---|
| `409 Conflict` | Another upload is already in progress |
| `413 Payload Too Large` | File exceeds `MAX_UPLOAD_BYTES` |
| `422 Unprocessable Entity` | Invalid extension, empty file, or corrupt content |
| `503 Service Unavailable` | Ollama is not reachable for embedding |

### Rate limit
5 requests per minute per IP.

---

## `POST /ingest/collections/{name}/clear`

Clears all documents from a ChromaDB collection. Idempotent.

### Path parameters
| Parameter | Type | Description |
|---|---|---|
| `name` | string | Collection name: `whd_tickets` or `kb_articles` |

### Response `200 OK`
```json
{
  "status": "ok",
  "collection": "kb_articles"
}
```

### Response `404 Not Found` — Invalid collection name
```json
{
  "detail": "Unknown collection: foo"
}
```

---

## `POST /ingest/url`

Fetches a URL server-side, extracts text content, chunks it, and ingests into ChromaDB. Shares the upload concurrency semaphore (one ingestion at a time).

### Request Body
```json
{
  "url": "https://learn.microsoft.com/en-us/windows-server/networking/802-1x"
}
```

### Request fields
| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string (URL) | yes | The URL to fetch and ingest (http/https only) |

### Response `200 OK`
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

### Response fields
| Field | Type | Description |
|---|---|---|
| `url` | string | The URL that was fetched |
| `collection` | string | Target ChromaDB collection (always `kb_articles`) |
| `chunks_ingested` | integer | Number of text chunks stored |
| `processing_time_ms` | integer | Total processing time |
| `title` | string \| null | Page title extracted from HTML |
| `warning` | string \| null | Warning message (e.g., no content extracted) |

### Error responses
| Status | Condition |
|---|---|
| `409 Conflict` | Another ingestion is already in progress |
| `413 Payload Too Large` | Response exceeds 5 MB |
| `422 Unprocessable Entity` | SSRF violation (private IP), unsupported Content-Type, invalid URL, or fetch failure |
| `503 Service Unavailable` | Ollama is not reachable for embedding |

### SSRF prevention
URLs are validated before fetching:
- Scheme must be `http` or `https`
- Hostname is resolved via DNS and checked against private IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16`, `::1`, `fe80::/10`)
- IPv4-mapped IPv6 addresses (e.g., `::ffff:127.0.0.1`) are detected and blocked
- Redirects are followed manually (max 10 hops), with SSRF re-validation on every hop
- Content-Type must be `text/html`, `text/plain`, or `application/xhtml+xml`

### Rate limit
5 requests per minute per IP.

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
