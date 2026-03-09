# Architecture — AI Helpdesk Assistant

## Overview

The AI Helpdesk Assistant is a three-part system:
1. A **Microsoft Edge browser extension** (Manifest V3) that reads WHD ticket pages and hosts the React UI sidebar
2. A **Native Messaging Host** (`native_host.py`) that bridges the extension to OS-level process management — starting/stopping llama-server and the FastAPI backend
3. A **Python FastAPI backend** that runs locally, orchestrates RAG retrieval, and calls llama-server (llama.cpp) for inference

All processing is local — no data leaves the machine (Microsoft Learn search is optional and read-only).

## Component Diagram

```
┌──────────────────────────────────────────────────────┐
│                Edge Browser Extension                 │
│  ┌─────────────────┐  ┌────────────────────────────┐ │
│  │  Sidebar Panel  │  │   Content Script           │ │
│  │  (React UI)     │  │  - Reads ticket DOM        │ │
│  │  - Chat/reply   │  │  - Injects reply text      │ │
│  │  - Insert btn   │  │  - MutationObserver (300ms)│ │
│  └────────┬────────┘  └──────────┬─────────────────┘ │
│           │   Background SW (relay + native msg)      │
│           │   └─ chrome.runtime.connectNative(...)    │
└───────────┼──────────────────────┬────────────────────┘
            │                      │ Native messaging (stdio)
            │               ┌──────▼──────────────────┐
            │               │  native_host.py          │
            │               │  - Manages llama-server  │
            │               │  - Manages FastAPI       │
            │               │  - Auto-tune GPU/RAM     │
            │               └──────┬──────────────────┘
            │ fetch (SSE)          │ subprocess
┌───────────▼──────────────────────▼──────────────────┐
│         Python FastAPI Backend (port 8765)            │
│  - RAG orchestration   - Prompt assembly              │
│  - ChromaDB retrieval  - SSE streaming                │
│  - ASGI middleware     - Cookie sessions              │
└──────────┬─────────────────────┬─────────────────────┘
           │                     │
┌──────────▼──────────┐ ┌────────▼───────────────┐
│  llama-server (x2)  │ │   ChromaDB (local)     │
│  :11435 chat model  │ │  - whd_tickets         │
│  :11436 embed model │ │  - kb_articles         │
└─────────────────────┘ │  - rated_replies       │
                        └────────────────────────┘
```

## Extension Architecture

### Service Worker (`background/service-worker.ts`)
- Acts as the message relay hub between sidebar and content script
- Opens the side panel when the toolbar button is clicked or `Alt+Shift+H` is pressed
- Relays `INSERT_REPLY` messages from sidebar → content script
- Relays `TICKET_DATA_UPDATED` messages from content script → sidebar
- Manages the native messaging port (`chrome.runtime.connectNative("com.anthropic.assistant")`) for backend lifecycle control

### Content Script (`content/`)
- Injected on WHD ticket pages (URL pattern + DOM marker detection)
- `dom-reader.ts`: Extracts ticket fields using a selector config with fallback chains (defined in `src/shared/constants.ts`)
- `dom-inserter.ts`: Injects generated text into the reply textarea using the native setter trick
- `sidebar-host.ts`: Manages the MutationObserver for WHD's partial DOM refreshes (debounced at 300ms)

### Sidebar (`sidebar/`)
- React 18 app rendered in the Edge Side Panel
- Zustand store for global state (ticket data, reply, loading state, settings)
- Hooks: `useTicketData`, `useGenerateReply`, `useSettings`
- Components: `ReplyPanel`, `TicketContext`, `InsertButton`, `ModelSelector`, `SkeletonLoader`, `ErrorState`
- SSE streaming for `/generate` responses — reply text streams in as it is generated

### Options Page (`options/`)
- Standalone React app rendered at `chrome://extensions` options page
- Persists settings to `chrome.storage.sync`

### KB Management SPA (`management/`)
- Standalone React app served at `/manage` on the backend
- Full CRUD for KB articles with search, tagging, pagination, and bulk import
- Uses TanStack Query for data fetching
- Authenticated via HttpOnly cookie sessions (`/auth/login` → `whd_session` cookie)
- Built as a separate Vite pass, output deployed to `backend/static/manage/`

## Native Messaging Lifecycle

The background service worker uses Chrome Native Messaging to manage backend processes:

1. Extension calls `chrome.runtime.connectNative("com.anthropic.assistant")`
2. `native_host.py` receives commands over stdin (4-byte length-prefixed JSON)
3. Supported actions: `start_backend`, `stop_backend`, `start_llm`, `stop_llm`, `get_token`
4. On `start_backend`: native host spawns llama-server (x2) and uvicorn as subprocesses
5. Auto-tune: detects RAM (kernel32) + VRAM (registry/CIM) to calculate `--n-gpu-layers` and `--ctx-size`
6. On extension disconnect or `stop_backend`: terminates all child processes via PID

## Backend Architecture

### FastAPI Application (`app/main.py`)
- Lifespan handler initializes shared httpx clients, ChromaDB, and singleton services
- Pure ASGI middleware stack (no BaseHTTPMiddleware): SecurityHeaders → CORS → SizeLimit → RateLimit → APIToken → CSRF
- Serves the Management SPA static files at `/manage`

### Routers

| Route | Method | Purpose |
|---|---|---|
| `/health` | GET | Basic readiness check (public) |
| `/health/detail` | GET | Detailed status — ChromaDB collections, server connectivity (auth-gated) |
| `/health/startup-phase` | GET | Startup progress reporting for extension |
| `/generate` | POST | LLM reply generation with RAG context (SSE streaming) |
| `/generate/review` | POST | Review/rewrite existing reply (SSE streaming) |
| `/models` | GET | Available GGUF model listing |
| `/llm/switch` | POST | Hot-swap LLM model (kills + restarts llama-server on :11435) |
| `/llm/stop` | POST | Stop LLM server |
| `/ingest/upload` | POST | File upload ingestion (PDF, HTML, JSON, CSV) |
| `/ingest/url` | POST | URL ingestion with SSRF prevention |
| `/kb/*` | CRUD | Article CRUD, tagging, pagination, management |
| `/auth/login` | POST | Exchange API token for HttpOnly session cookie |
| `/auth/logout` | POST | Clear session cookie |
| `/auth/check` | GET | Validate session |
| `/feedback` | POST/DELETE | Reply rating storage (thumbs up/down + text) |
| `/download/models` | POST | Model download with SHA-256 verification + progress SSE |
| `/settings` | GET/PUT | Runtime config (sampling params, prompt suffix) |

### Services

| Service | Responsibility |
|---|---|
| `LLMService` | Text completions via llama-server `/v1/chat/completions`, supports SSE streaming, retry logic |
| `EmbedService` | Embeddings via llama-server `/v1/embeddings` (nomic-embed-text), dual async/sync clients |
| `RAGService` | ChromaDB query, two-phase retrieval (tag filter → similarity backfill), merges whd_tickets + kb_articles |
| `MicrosoftDocsService` | Live search at generation time, domain-locked to `learn.microsoft.com`, 5-min LRU cache |
| `ModelDownloadService` | Downloads GGUF models with SHA-256 hash verification, streams progress via SSE |
| `SessionStore` | In-memory session management with `asyncio.Lock`, periodic sweep of expired sessions |
| `AuditService` | Structured JSON logging for security-sensitive actions (login, delete, shutdown) |

### Middleware Stack (Pure ASGI)

All middleware is pure ASGI (`__call__(scope, receive, send)`) — no `BaseHTTPMiddleware`, streaming-safe, no body buffering.

| Middleware | Purpose |
|---|---|
| Security Headers | `X-Content-Type-Options`, `X-Frame-Options`, `Cache-Control: no-store`, `Referrer-Policy` |
| CORS | Locked to extension origin (`chrome-extension://<ID>`) |
| Request Size Limit | 64 KB for API requests, 50 MB for file uploads |
| Rate Limiting | 20/min for `/generate`, 5/min for `/ingest` |
| API Token Auth | `X-Extension-Token` header OR `whd_session` HttpOnly cookie |
| CSRF Protection | State-changing endpoints require valid CSRF token |

### Data Flow for Reply Generation (SSE Streaming)

```
1. Sidebar sends ticket fields to backend POST /generate
2. Backend opens an SSE (text/event-stream) connection
3. embed_service embeds the ticket subject+description
4. rag_service queries whd_tickets and kb_articles collections (parallel via asyncio.gather)
5. ms_docs_service searches Microsoft Learn (in parallel with RAG, if enabled)
6. Top-k results merged and ranked by similarity score
7. llm_service assembles grounded prompt with few-shot examples from rated replies
8. llama-server generates reply; tokens stream back via SSE events
9. Sidebar displays reply text progressively as tokens arrive
10. User clicks Insert → INSERT_REPLY message flows: sidebar → background SW → content script
11. dom-inserter.ts injects text into WHD textarea
```

## Security Model

- Backend CORS allows only `chrome-extension://<ID>` — never `*`
- Extension `host_permissions`: only `http://localhost:8765/*`
- Two auth methods: API token header (`X-Extension-Token`) for extension, HttpOnly cookie session for Management SPA
- CSRF protection on all state-changing endpoints
- No secrets committed — `.env` file gitignored
- Content script sanitizes all DOM interactions — no dynamic code execution or `innerHTML` with untrusted content
- All request fields validated by Pydantic
- SHA-256 verification on model downloads
- Structured audit logging for security-sensitive actions
- Pure ASGI middleware — streaming-safe, no body buffering
