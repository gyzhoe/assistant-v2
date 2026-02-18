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
  "stream": false
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
