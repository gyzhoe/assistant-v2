# Architecture — AI Helpdesk Assistant

## Overview

The AI Helpdesk Assistant is a two-part system:
1. A **Microsoft Edge browser extension** (Manifest V3) that reads WHD ticket pages and hosts the React UI sidebar
2. A **Python FastAPI backend** that runs locally, orchestrates RAG retrieval, and calls Ollama for inference

All processing is local — no data leaves the machine.

## Component Diagram

```
┌──────────────────────────────────────────────────┐
│              Edge Browser Extension               │
│  ┌─────────────────┐  ┌────────────────────────┐ │
│  │  Sidebar Panel  │  │   Content Script       │ │
│  │  (React UI)     │  │  - Reads ticket DOM    │ │
│  │  - Chat/reply   │  │  - Injects reply text  │ │
│  │  - Insert btn   │  │  - MutationObserver    │ │
│  └────────┬────────┘  └──────────┬─────────────┘ │
│           │   Background SW (relay)               │
└───────────┼──────────────────────────────────────┘
            │ fetch → http://localhost:8765
┌───────────▼──────────────────────────────────────┐
│         Python FastAPI Backend (port 8765)        │
│  - RAG orchestration   - Prompt assembly          │
│  - ChromaDB retrieval  - Ollama client            │
└──────────┬─────────────────────┬─────────────────┘
           │                     │
┌──────────▼──────────┐ ┌────────▼───────────────┐
│   Ollama Server     │ │   ChromaDB (local)     │
│  llama3.2:3b (gen)  │ │  - whd_tickets         │
│  nomic-embed-text   │ │  - kb_articles         │
└─────────────────────┘ └────────────────────────┘
```

## Extension Architecture

### Service Worker (`background/service-worker.ts`)
- Acts as the message relay hub between sidebar and content script
- Opens the side panel when the toolbar button is clicked or `Alt+Shift+H` is pressed
- Relays `INSERT_REPLY` messages from sidebar → content script
- Relays `TICKET_DATA_UPDATED` messages from content script → sidebar

### Content Script (`content/`)
- Injected on WHD ticket pages (URL pattern + DOM marker detection)
- `dom-reader.ts`: Extracts ticket fields using a selector config with fallback chains
- `dom-inserter.ts`: Injects generated text into the reply textarea using the native setter trick
- `sidebar-host.ts`: Manages the MutationObserver for WHD's partial DOM refreshes

### Sidebar (`sidebar/`)
- React 18 app rendered in the Edge Side Panel
- Zustand store for global state (ticket data, reply, loading state, settings)
- Hooks: `useTicketData`, `useGenerateReply`, `useSettings`
- Components: `ReplyPanel`, `TicketContext`, `InsertButton`, `ModelSelector`, `SkeletonLoader`, `ErrorState`

### Options Page (`options/`)
- Standalone React app rendered at `chrome://extensions` options page
- Persists settings to `chrome.storage.sync`

## Backend Architecture

### FastAPI Application (`app/main.py`)
- Lifespan handler initializes ChromaDB and verifies Ollama connectivity
- CORS restricted to the exact extension origin

### Routers
| Route | Purpose |
|---|---|
| `GET /health` | System status check |
| `POST /generate` | Main RAG + LLM inference endpoint |
| `GET /models` | Lists available Ollama models |
| `POST /ingest` | Triggers ingestion (for future web UI) |

### Services
- `embed_service.py`: Embeds text using `nomic-embed-text` via Ollama
- `rag_service.py`: Queries ChromaDB collections, merges and ranks results
- `llm_service.py`: Sends prompt to Ollama, returns completion

### Data Flow for Reply Generation

```
1. Sidebar sends ticket fields to backend POST /generate
2. embed_service embeds the ticket subject+description
3. rag_service queries whd_tickets and kb_articles collections
4. Top-k results merged and ranked by similarity score
5. llm_service assembles prompt + context docs
6. Ollama generates reply
7. Backend returns { reply, context_docs, latency_ms }
8. Sidebar displays reply; user clicks Insert
9. INSERT_REPLY message flows: sidebar → background SW → content script
10. dom-inserter.ts injects text into WHD textarea
```

## Security Model

- Backend CORS allows only `chrome-extension://<ID>` — never `*`
- Extension `host_permissions`: only `http://localhost:8765/*`
- No secrets committed — `.env` file gitignored
- Content script never uses `eval()` or `innerHTML` with untrusted content
- All request fields validated by Pydantic
