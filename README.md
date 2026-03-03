# AI Helpdesk Assistant

> **Proof of Concept** — This project is a working PoC. The current architecture runs the AI backend locally on the technician's machine via [Ollama](https://ollama.com). The intended end goal is to move AI inference to a shared server or cloud instance (e.g. Azure OpenAI, a self-hosted GPU server), with the Edge extension connecting to that remote backend instead. The local-Ollama setup exists to validate the concept without infrastructure costs.

A local AI assistant for SolarWinds Web Help Desk (on-premises), delivered as a Microsoft Edge browser extension. All AI inference currently runs locally via [Ollama](https://ollama.com) — no data leaves your network.

## Installation

**One-liner (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/gyzhoe/assistant-v2/main/scripts/install.ps1 | iex
```

**Via Scoop:**
```powershell
scoop bucket add assistant https://github.com/gyzhoe/assistant-v2 -p scoop
scoop install ai-helpdesk-assistant
```

**Manual:** Download the latest `.exe` from [GitHub Releases](https://github.com/gyzhoe/assistant-v2/releases/latest) and run it.

## What It Does

When a technician opens a WHD ticket, the assistant:
1. **Reads** the ticket subject, description, requester, category, and status automatically
2. **Retrieves** relevant context from past resolved tickets and KB articles (RAG via ChromaDB)
3. **Generates** a professional reply suggestion using a local LLM (default: `llama3.2:3b`)
4. **Inserts** the reply into the WHD reply textarea with one click

### Knowledge Import

The sidebar includes a **Knowledge Base** panel for importing documents directly into ChromaDB — no CLI required:
- Drag-and-drop file upload (PDF, HTML, JSON, CSV)
- URL ingestion: paste a URL and the backend fetches, extracts, and chunks it
- Progress tracking with per-file status and cancel support
- Collection management: view document counts and clear collections

### Microsoft Learn Live Search

When generating a reply, the backend searches [Microsoft Learn](https://learn.microsoft.com) for documentation matching the ticket's subject and category. Results are included alongside your local KB articles as additional RAG context — no pre-ingestion required. This runs in parallel with the local ChromaDB lookup, so it adds no latency when the network is fast. Gracefully degrades if the search fails.

## Architecture

```
Edge Extension (sidebar + content script)
        ↕ fetch → http://localhost:8765
FastAPI Backend
        ↕                      ↕
   Ollama (LLM + embed)   ChromaDB (vector store)
```

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| [Node.js](https://nodejs.org) | ≥ 20 | Extension build |
| [Python](https://python.org) | 3.13 | Backend (3.14 not supported) |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager |
| [Ollama](https://ollama.com) | latest | Local LLM inference |
| Microsoft Edge | latest | Extension host |

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd assistant
npm install

# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start backend
cd backend
python -m uv sync --dev --python 3.13
python -m uv run uvicorn app.main:app --port 8765 --reload

# Terminal 3: Build extension
npm run build

# Load extension in Edge:
# 1. Open edge://extensions
# 2. Enable Developer mode
# 3. Click "Load unpacked" → select extension/dist/
# 4. Open a WHD ticket → press Alt+Shift+H
```

## Ingest Your Data

### Via Sidebar (recommended)

1. Open the sidebar (`Alt+Shift+H`) on any WHD ticket
2. Expand the **Knowledge Base** panel
3. Drag-and-drop files (PDF, HTML, JSON, CSV) into the Import tab
4. Click **Import** and wait for processing to complete

### Via CLI

```bash
cd backend

# Import resolved tickets (WHD JSON/CSV export)
python -m uv run python -m ingestion.cli ingest-tickets export.json

# Import KB articles
python -m uv run python -m ingestion.cli ingest-kb-html ./kb_articles/
python -m uv run python -m ingestion.cli ingest-kb-pdf ./kb_pdfs/

# Check ingestion status
python -m uv run python -m ingestion.cli status
```

## Development

```bash
# Run all tests
npx --workspace=extension vitest run    # Extension unit tests (60 tests)
cd backend && python -m uv run pytest tests/ -v  # Backend tests (152 tests)

# Type checking
npm run typecheck
cd backend && python -m uv run mypy app/ ingestion/

# Linting
npm run lint
cd backend && python -m uv run ruff check .

# Production build
npm run build
```

## Project Structure

```
assistant/
├── extension/      TypeScript + React 18 + Vite + Manifest V3
├── backend/        Python FastAPI + ChromaDB + Ollama (httpx)
├── docs/           Architecture docs, API contract, WHD DOM selectors
├── scripts/        Developer setup script
└── .github/        CI workflows (backend + extension + Claude review)
```

## Configuration

The extension options page (right-click extension icon → Options) lets you configure:
- Backend URL (default: `http://localhost:8765`)
- LLM model selection
- DOM selector overrides for custom WHD installations
- Prompt suffix customization
- Theme (light/dark/system)

Backend configuration via `.env` in `backend/`:
```env
OLLAMA_BASE_URL=http://localhost:11434
CHROMA_PATH=./chroma_data
CORS_ORIGIN=chrome-extension://<your-extension-id>
DEFAULT_MODEL=llama3.2:3b
API_TOKEN=<generated-secret>
MAX_UPLOAD_BYTES=52428800
```

## Security

- All inference is local — no data sent to external services (Microsoft Learn search is opt-in)
- CORS is locked to your specific extension origin (not `*`)
- API token authentication via `X-Extension-Token` header
- Rate limiting: 20 req/min for generation, 5 req/min for file/URL ingestion
- Request size limits: 64 KB for API calls, 50 MB for file uploads, 5 MB for URL fetch
- Concurrency control: single ingestion at a time (409 on concurrent attempts)
- SSRF prevention for URL ingestion: private IP blocking, redirect re-validation, scheme whitelist
- Backend validates all inputs via Pydantic
- See [Security Guide](docs/security.md) for production hardening

## License

MIT

## Acknowledgments

This project is built on excellent open-source software. Key dependencies include:

- **[Ollama](https://ollama.com)** — local LLM inference engine
- **[ChromaDB](https://github.com/chroma-core/chroma)** — vector store for RAG
- **[FastAPI](https://fastapi.tiangolo.com)** — Python web framework
- **[React](https://react.dev)** — UI library
- **[Radix UI](https://www.radix-ui.com)** — accessible component primitives
- **[Tailwind CSS](https://tailwindcss.com)** — utility-first CSS framework
- **[Vite](https://vitejs.dev)** — build tool and dev server

See [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) for the full list of dependencies and their licenses.
