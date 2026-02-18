# AI Helpdesk Assistant

A local AI assistant for SolarWinds Web Help Desk (on-premises), delivered as a Microsoft Edge browser extension. All AI inference runs locally via [Ollama](https://ollama.com) — no data leaves your network.

## What It Does

When a technician opens a WHD ticket, the assistant:
1. **Reads** the ticket subject, description, requester, category, and status automatically
2. **Retrieves** relevant context from past resolved tickets and KB articles (RAG via ChromaDB)
3. **Generates** a professional reply suggestion using a local LLM (default: `llama3.2:3b`)
4. **Inserts** the reply into the WHD reply textarea with one click

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
| [Python](https://python.org) | 3.11+ | Backend |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager |
| [Ollama](https://ollama.com) | latest | Local LLM inference |
| Microsoft Edge | latest | Extension host |

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd assistant
bash scripts/dev-setup.sh

# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start backend
cd backend
uv run uvicorn app.main:app --port 8765 --reload

# Terminal 3: Build extension
cd extension
npm run build

# Load extension in Edge:
# 1. Open edge://extensions
# 2. Enable Developer mode
# 3. Click "Load unpacked" → select extension/dist/
# 4. Open a WHD ticket → press Alt+Shift+H
```

## Ingest Your Data

```bash
cd backend

# Import resolved tickets (WHD JSON/CSV export)
uv run python -m ingestion.cli ingest-tickets export.json

# Import KB articles
uv run python -m ingestion.cli ingest-kb-html ./kb_articles/
uv run python -m ingestion.cli ingest-kb-pdf ./kb_pdfs/

# Check ingestion status
uv run python -m ingestion.cli status
```

## Development

```bash
# Run all tests
cd extension && npm test          # Vitest unit tests
cd backend && uv run pytest -v    # Python tests
cd extension && npx playwright test  # E2E tests

# Type checking
cd extension && npm run typecheck
cd backend && uv run mypy app/ ingestion/

# Linting
cd extension && npm run lint
cd backend && uv run ruff check .
```

## Project Structure

```
assistant/
├── extension/      TypeScript + React 18 + Vite + Manifest V3
├── backend/        Python FastAPI + LangChain + ChromaDB
├── docs/           Architecture docs, API contract, WHD DOM selectors
├── scripts/        Developer setup script
└── .github/        CI workflows, issue/PR templates, Dependabot
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
```

## Security

- All inference is local — no data sent to external services
- CORS is locked to your specific extension origin (not `*`)
- No API keys or credentials are stored in the extension
- Backend validates all inputs via Pydantic

## License

MIT
