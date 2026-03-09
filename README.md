# AI Helpdesk Assistant

> **Proof of Concept** — This project is a working PoC. The current architecture runs the AI backend locally on the technician's machine via [llama.cpp](https://github.com/ggml-org/llama.cpp). The intended end goal is to move AI inference to a shared server or cloud instance (e.g. Azure OpenAI, a self-hosted GPU server), with the Edge extension connecting to that remote backend instead. The local llama.cpp setup exists to validate the concept without infrastructure costs.

A local AI assistant for [SolarWinds Web Help Desk](https://www.solarwinds.com/web-help-desk) (on-premises), delivered as a Microsoft Edge browser extension with a Python backend. All AI inference runs locally via llama.cpp — no data leaves your network.

## Installation

**One-liner (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/gyzhoe/assistant-v2/main/scripts/install.ps1 | iex
```

**Manual:** Download the latest `.exe` from [GitHub Releases](https://github.com/gyzhoe/assistant-v2/releases/latest) and run it.

The installer bundles everything needed to run: Python 3.13, llama-server (with GPU auto-detection), backend dependencies, and the Edge extension. No prerequisites required.

### GPU Auto-Detection

The installer automatically detects your GPU and installs the optimal llama-server build:

| GPU | Build | Notes |
|---|---|---|
| NVIDIA (Pascal / GTX 10xx and newer) | CUDA 12.4 | Best performance |
| AMD Radeon / Intel Arc | Vulkan | Universal GPU support |
| No supported GPU | CPU | Fallback, slower but functional |

After install:
1. Load the extension in Edge: `edge://extensions` → Developer mode → Load unpacked → select the extension folder
2. Download the AI models: right-click the extension icon → **Options** → **LLM Models** section
3. Open a WHD ticket and press `Alt+Shift+H` to open the sidebar

## What It Does

When a technician opens a WHD ticket, the assistant:
1. **Reads** the ticket subject, description, requester, category, and status from the page automatically
2. **Retrieves** relevant context from past resolved tickets and KB articles via RAG (ChromaDB)
3. **Searches** [Microsoft Learn](https://learn.microsoft.com) for relevant documentation in parallel
4. **Generates** a professional reply suggestion using a local LLM (default: `qwen3.5:9b`), streaming tokens to the sidebar in real time via Server-Sent Events (SSE)
5. **Inserts** the reply into the WHD reply textarea with one click

### Knowledge Base

- **Sidebar import** — drag-and-drop file upload (PDF, HTML, JSON, CSV) and URL ingestion directly from the sidebar
- **Management page** — full KB management SPA at `/manage` for browsing, tagging, and deleting articles
- **Two-phase RAG** — articles are tagged on import; retrieval filters by tag relevance before scoring by similarity
- **Microsoft Learn** — live search runs in parallel with local KB lookups, adding documentation context without pre-ingestion

### Feedback Loop

Technicians can rate generated replies (thumbs up/down) with optional text feedback. Positively-rated replies are stored and used as additional RAG context for future generations, improving quality over time.

## Architecture

```
Edge Extension
├── Content Script ─── reads WHD DOM, inserts replies
├── Background SW ──── relays messages, native messaging lifecycle
└── Sidebar UI ─────── React + Zustand, calls backend API
        ↕ fetch → http://localhost:8765
        ↕ chrome.runtime.connectNative
native_host.py ─────── manages llama-server + backend processes
        ↕ start/stop via native messaging
FastAPI Backend (async, pure ASGI middleware)
├── /generate ───── LLM reply generation with RAG context (SSE streaming)
├── /ingest ─────── file upload + URL ingestion pipeline
├── /kb ─────────── article CRUD, tagging, management
├── /auth ───────── HttpOnly cookie sessions
├── /health ─────── readiness + startup phase reporting
├── /models ─────── available GGUF model listing + runtime switching
├── /llm/switch ─── hot-swap LLM model (kills + restarts llama-server)
└── /feedback ───── reply rating storage
        ↕                      ↕
   llama-server (LLM + embed)  ChromaDB (vector store)
```

The extension uses a three-layer message relay: content script ↔ background service worker ↔ sidebar. Messages are typed via discriminated unions in `src/shared/messages.ts`. The background service worker manages process lifecycle via Chrome native messaging — sending `start_backend` / `stop_backend` commands to `native_host.py`, which spawns and monitors llama-server and the FastAPI backend. The backend runs pure ASGI middleware (no `BaseHTTPMiddleware`) for streaming-safe request handling.

See [Architecture Guide](docs/architecture.md) and [API Contract](docs/api-contract.md) for details.

## Prerequisites

Only needed for development — the installer handles everything for end users.

| Tool | Version | Purpose |
|---|---|---|
| [Node.js](https://nodejs.org) | ≥ 20 | Extension build |
| [Python](https://python.org) | 3.13 | Backend runtime (3.14 breaks chromadb) |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | latest | Local LLM inference (`llama-server`) |
| Microsoft Edge | latest | Extension host |

## Quick Start

```bash
# Clone
git clone https://github.com/gyzhoe/assistant-v2.git
cd assistant-v2
npm install

# Terminal 1: LLM server (download llama-server from llama.cpp releases)
# Start chat model on port 11435:
llama-server -m models/Qwen3.5-9B-Q4_K_M.gguf --port 11435 --n-gpu-layers 99
# Start embedding model on port 11436 (separate terminal):
llama-server -m models/nomic-embed-text-v1.5.f16.gguf --port 11436 --embedding --n-gpu-layers 99

# Terminal 2: Backend
cd backend
python -m uv sync --dev --python 3.13
python -m uv run uvicorn app.main:app --port 8765 --reload

# Terminal 3: Extension
npm run build    # or: npm run dev (watch mode)

# Load in Edge:
# edge://extensions → Developer mode → Load unpacked → extension/dist/
# Open a WHD ticket → Alt+Shift+H
```

## Ingest Your Data

### Via Sidebar (recommended)

1. Open the sidebar (`Alt+Shift+H`) on any WHD ticket
2. Expand the **Knowledge Base** panel
3. Drag-and-drop files (PDF, HTML, JSON, CSV) or paste a URL
4. Click **Import** and wait for processing

### Via CLI

```bash
cd backend

# Resolved tickets (WHD JSON/CSV export)
python -m uv run python -m ingestion.cli ingest-tickets export.json

# KB articles
python -m uv run python -m ingestion.cli ingest-kb-html ./kb_articles/
python -m uv run python -m ingestion.cli ingest-kb-pdf ./kb_pdfs/

# Check status
python -m uv run python -m ingestion.cli status
```

## Development

### Testing

```bash
# Extension unit tests (~237 tests)
npx --workspace=extension vitest run

# Backend tests (~459 tests)
cd backend && python -m uv run pytest tests/ -v --tb=short

# E2E tests — Management SPA (16 tests)
npx --workspace=extension playwright test

# Run a single test file
npx --workspace=extension vitest run tests/unit/someFile.test.ts
cd backend && python -m uv run pytest tests/test_health.py -v
```

### Linting and Type Checking

```bash
# Extension
npm run typecheck     # tsc --noEmit (strict, no any)
npm run lint          # eslint, zero warnings

# Backend
cd backend
python -m uv run mypy app/ ingestion/   # strict mode
python -m uv run ruff check .           # line length 100
```

### Build

```bash
npm run build    # two-stage Vite build (sidebar ESM + content script IIFE)
npm run dev      # watch mode
```

## Project Structure

```
assistant/
├── extension/
│   └── src/
│       ├── sidebar/        Sidebar UI — React + Zustand + TanStack Query
│       ├── management/     KB Management SPA (/manage page)
│       ├── content/        Content script — WHD DOM reader + reply inserter
│       ├── background/     Service worker — message relay + native messaging
│       ├── options/        Extension options page
│       ├── shared/         Message types, constants, utilities
│       └── lib/            Shared UI components
├── backend/
│   └── app/
│       ├── routers/        API endpoints (generate, ingest, kb, auth, health, feedback, models)
│       ├── services/       LLM, embedding, RAG, Microsoft Docs, session store, audit
│       ├── middleware/      CSRF protection, security (rate limiting, size limits, CORS, auth)
│       └── config.py       pydantic-settings configuration
├── installer/              Inno Setup script + assets
├── scripts/                Install script, dev setup
├── docs/                   Architecture, API contract, security guide
└── .github/workflows/      CI (backend + extension) + release pipeline
```

## Configuration

### Extension Options

Right-click the extension icon → **Options**:
- Backend URL (default: `http://localhost:8765`)
- LLM model selection (auto-populated from available GGUF models)
- DOM selector overrides for custom WHD installations
- Prompt suffix customization
- Theme (light / dark / system)

### Backend Environment

Create `backend/.env`:
```env
LLM_BASE_URL=http://localhost:11435
EMBED_BASE_URL=http://localhost:11436
CHROMA_PATH=./chroma_data
CORS_ORIGIN=chrome-extension://<your-extension-id>
DEFAULT_MODEL=qwen3.5:9b
API_TOKEN=<generated-secret>
MAX_UPLOAD_BYTES=52428800
```

## Security

- All inference is local — no data sent to external services (Microsoft Learn search is opt-in)
- CORS locked to your specific extension origin (never `*`)
- API token auth via `X-Extension-Token` header + HttpOnly cookie sessions
- CSRF protection on state-changing endpoints
- Rate limiting: 20 req/min generation, 5 req/min ingestion
- Request size limits: 64 KB API calls, 50 MB file uploads, 5 MB URL fetch
- SSRF prevention for URL ingestion: private IP blocking, redirect validation, scheme whitelist
- Input validation via Pydantic on all endpoints
- Audit logging for security-sensitive actions
- SHA-256 hash verification for model downloads
- See [Security Guide](docs/security.md) for production hardening

## License

MIT — See [LICENSE](installer/assets/license.txt)

## Acknowledgments

This project is built on excellent open-source software. Key dependencies include:

- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** — local LLM inference engine
- **[ChromaDB](https://github.com/chroma-core/chroma)** — vector store for RAG
- **[FastAPI](https://fastapi.tiangolo.com)** — Python web framework
- **[React](https://react.dev)** — UI library
- **[Radix UI](https://www.radix-ui.com)** — accessible component primitives
- **[Tailwind CSS](https://tailwindcss.com)** — utility-first CSS framework
- **[Zustand](https://github.com/pmndrs/zustand)** — lightweight state management
- **[Vite](https://vitejs.dev)** — build tool and dev server
- **[Qwen 3.5](https://huggingface.co/Qwen)** — default language model (via GGUF)
- **[nomic-embed-text](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF)** — embedding model
- **[Inno Setup](https://jrsoftware.org/isinfo.php)** — Windows installer framework

See [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) for the full list of dependencies and their licenses.
