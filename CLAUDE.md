# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local AI assistant for SolarWinds Web Help Desk (on-prem). Delivered as a Microsoft Edge
browser extension (Manifest V3) with a Python FastAPI backend. All AI inference is local
via Ollama — no cloud calls are ever made.

```text
Edge Extension (sidebar UI + content script)
        ↕ chrome.runtime messages
    Background Service Worker (relay)
        ↕ fetch → http://localhost:8765
FastAPI Backend
        ↕                      ↕
   Ollama (LLM + embed)   ChromaDB (vector store)
```

---

## Build & Dev Commands

### Extension (TypeScript + React 18 + Vite)

```bash
npm install                              # install deps (workspace root)
npm run build                            # production build (runs two Vite passes)
npm run dev                              # watch mode
npm run typecheck                        # tsc --noEmit
npm run lint                             # eslint, zero warnings allowed
npx --workspace=extension vitest run     # all unit tests
npx --workspace=extension vitest run tests/unit/someFile.test.ts  # single test file
npx --workspace=extension vitest         # watch mode
npx --workspace=extension playwright test  # E2E tests
```

### Backend (Python 3.13 + FastAPI)

```bash
cd backend
python -m uv sync --dev --python 3.13   # install deps (creates .venv)
python -m uv run uvicorn app.main:app --port 8765 --reload  # dev server
python -m uv run pytest tests/ -v --tb=short                # all tests
python -m uv run pytest tests/test_health.py -v              # single test file
python -m uv run pytest tests/ -k "test_name" -v             # single test by name
python -m uv run ruff check .           # lint
python -m uv run mypy app/ ingestion/   # type check
```

**Important:** Use `python -m uv`, not bare `uv`. Backend requires Python 3.13 — version 3.14 breaks chromadb/pydantic v1.

### Environment (WSL2)

This repo runs under WSL2 on Windows 11. Critical rules for agents:

- **NEVER run `find /` or `find /mnt/c`** — scanning the Windows C: drive through WSL2 takes 30+ minutes. Use `which`, `command -v`, or targeted paths instead.
- Python 3.14 (for MCP/tools): `~/.local/bin/python3.14` (on PATH)
- Python 3.13 (for backend): `python -m uv run` inside `backend/` — do NOT search for it
- `uvx` and `uv`: `~/.local/bin/uvx`, `~/.local/bin/uv` (on PATH)
- Installer scripts are PowerShell (Windows-only) — do not attempt to run `.ps1` files in WSL2

### Running Services

```bash
ollama serve                             # port 11435, models: qwen3.5:9b, nomic-embed-text
cd backend && python -m uv run uvicorn app.main:app --port 8765 --reload
```

### Data Ingestion

```bash
cd backend
python -m uv run python -m ingestion.cli ingest-tickets export.json
python -m uv run python -m ingestion.cli ingest-kb-html ./kb_articles/
python -m uv run python -m ingestion.cli ingest-kb-pdf ./kb_pdfs/
python -m uv run python -m ingestion.cli status
```

---

## Architecture

### Extension Message Flow

The extension uses a three-layer message relay (content script cannot talk directly to sidebar):

1. **Content script** (`src/content/`) — reads ticket data from WHD DOM, inserts replies
2. **Background service worker** (`src/background/`) — relays `chrome.runtime` messages between content script and sidebar
3. **Sidebar** (`src/sidebar/`) — React UI, Zustand store, calls backend API

All messages are typed via a discriminated union in `src/shared/messages.ts`:

- `ContentToSidebarMessage`: `TICKET_DATA_UPDATED`, `INSERT_SUCCESS`, `INSERT_FAILED`, `NOT_A_TICKET_PAGE`
- `SidebarToContentMessage`: `INSERT_REPLY`, `REQUEST_TICKET_DATA`

### Two-Stage Vite Build

The extension requires two separate Vite builds (`npm run build` runs both):

- **Main build** (`vite.config.ts`): sidebar HTML, options page, service worker — ESM output
- **Content script build** (`vite.config.content.ts`): IIFE format (MV3 content scripts don't support ES modules), `emptyOutDir: false` to preserve main build

### Backend Service Layer

- `LLMService` (`app/services/llm_service.py`): generates text via Ollama `/api/generate` using httpx (no LangChain)
- `EmbedService` (`app/services/embed_service.py`): generates embeddings via Ollama `/api/embeddings` (model: `nomic-embed-text`)
- `RAGService` (`app/services/rag_service.py`): queries two ChromaDB collections (`whd_tickets`, `kb_articles`), merges results by similarity score
- All blocking Ollama/ChromaDB calls wrapped in `asyncio.to_thread`
- Config via `pydantic-settings` in `app/config.py` (reads `.env`)

### Sidebar State Management

Zustand store at `src/sidebar/store/sidebarStore.ts` holds all sidebar state: ticket data, generation status, reply text, model selection. Hooks in `src/sidebar/hooks/` encapsulate specific behaviors (settings, theme, generation, ticket data).

### DOM Interaction (WHD-specific)

- Selectors with fallback chains defined in `src/shared/constants.ts` (`DEFAULT_SELECTORS`)
- User can override selectors via extension options page (stored in `chrome.storage.sync`)
- `dom-inserter.ts` uses the native setter trick to set textarea values (not `textarea.value = x`)
- MutationObserver debounced at 300ms (`OBSERVER_DEBOUNCE_MS`)
- WHD uses table-based layouts: `td.labelStandard` for labels, `select[id^="ProblemType_"]` for request types, `td.defaultFont` for client names

---

## Coding Rules

### TypeScript / Extension

- `strict: true` — no `any`, no `// @ts-ignore`
- No `console.log` in production — use `debugLog`/`debugError` from `src/shared/constants.ts` (gated on `import.meta.env.DEV`)
- Path alias: `@` → `extension/src/`

### Python / Backend

- Type hints on all functions, `mypy --strict`
- `ruff` for linting (rules: E, F, I, N, W, UP; line length 100)
- CORS origin locked to `chrome-extension://<ID>` — never `"*"` in production
- All async routes use `async def`

### Testing Gotchas

- jsdom lacks `scrollIntoView` — stub with `Element.prototype.scrollIntoView = vi.fn()`
- jsdom lacks `matchMedia` — stub with `vi.stubGlobal('matchMedia', ...)`
- `vi.restoreAllMocks()` undoes `vi.stubGlobal` — re-apply in `beforeEach` if using `resetModules`
- `chrome.storage.sync.get` key is `appSettings` (from `STORAGE_KEY_SETTINGS` constant)
- `chrome.runtime.sendMessage` mock must return a Promise (`.mockResolvedValue(undefined)`)
- Backend middleware tests need a separate app fixture via `create_app()` to test token auth
- `subprocess.CREATE_NO_WINDOW` only exists on Windows — use `sys.platform == "win32"` branch for mypy

---

## UX & Design

This is an enterprise tool used by helpdesk technicians handling 40+ tickets daily. Every UI change must feel intentional, polished, and fast.

### Design System
- **Fluent Design** — accent blue `#0078d4`, neutral grays from CSS custom properties (`--surface`, `--border`, `--muted`, `--accent`)
- **Component library:** Radix UI primitives + Tailwind CSS
- **No hardcoded colors.** Always use design tokens. No new CSS variables unless absolutely necessary.
- **Transitions:** 120ms standard (from `sidebar.css`). Collapsing panels, showing spinners, confirm dialogs — all animate.
- **Dark mode:** Every component must work in both themes. Test both.

### Interaction Standards
- Every interactive element needs **all states**: default, hover, focus-visible, active, disabled, loading, success, error
- Skeleton loaders (not spinners) for generation wait states; spinners acceptable for short operations (<3s)
- Sidebar never obscures ticket content — it's a tool, not a takeover
- Keyboard shortcut: `Alt+Shift+H` toggles sidebar
- **Modals** trap focus and auto-focus the safe action (Cancel, not Delete)
- **Test in the sidebar's narrow viewport** (~360px). Tooltips, modals, and spinners must fit without overflow.

### Copy & Messaging
- Error messages explain what went wrong AND what to do next
- Confirmations state the consequence clearly ("This will delete all 47 articles in this collection")
- Keep it concise — no jargon, no filler. Technicians are busy.
- Don't surprise users — if behavior changes, make it obvious with standard affordances

---

## Security

Enterprise environment handling sensitive data. Security is not optional.

- CORS restricted to exact extension origin in `config.py`
- Optional API token auth via `API_TOKEN` env var + `X-Extension-Token` header
- Rate limiting and request size limits via custom middleware (`app/middleware/security.py`)
- Extension `host_permissions` minimal: only `http://localhost:8765/*`
- Secrets stored in `chrome.storage.local` (never synced) via `STORAGE_KEY_SECRETS`
- **Validate all inputs.** Path params get regex constraints. Config values get type checks. User-facing strings get sanitized before logging.
- **Least privilege.** Don't expose more than needed — health returns minimal info unauthenticated, cookies have tightest flags, CSP is explicit.
- **No secrets in code, logs, or commits.** Hash or omit PII in logs. Never hardcode tokens. Follow OWASP top 10.
- **Audit trail.** Security-sensitive actions (login, delete, shutdown) must be logged with timestamp, client IP, and outcome.

---

## Git & CI

- **Commits:** Conventional Commits — `feat(extension):`, `fix(backend):`, `chore:`, `docs:`
- **Branches:** `feat/`, `fix/`, `chore/`, `docs/` off `main`
- **PRs:** CI must pass (backend: ruff + mypy + pytest; extension: typecheck + lint + test + build)
- **No force-push to main**
- **Worktrees** for parallel work: `../assistant-worktrees/<branch-name>`. One worktree per task, removed after PR merge. Always `git worktree list` before creating.
- **Releases:** semantic versioning, GitHub Release pipeline zips extension + attaches artifacts

---

## Workflow Reminders

### Before Writing Code

- **Read before editing** — never propose changes to code you haven't read
- **Use subagents/teams** for non-trivial tasks — keep the main conversation context clean by delegating research, implementation, and review to Agent tool subagents or teams
- **Match agent types to their tools** — read-only agents (Explore, Plan) cannot edit files; use general-purpose for implementation. Always assign `mode: "bypassPermissions"` to agents that need to run tests or shell commands. Verify each agent's available tools before assigning tasks.
- **Check existing patterns** — match the style, naming, and structure of surrounding code

### During Development

- **Never push directly to main** — always create a branch (`feat/`, `fix/`, `chore/`, `docs/`) and open a PR
- **Conventional Commits** — `feat(extension):`, `fix(backend):`, `chore:`, `docs:` — no exceptions
- **Update CHANGELOG.md** in the feature branch before merging (not as a post-merge step)
- **Check installer** (`setup.iss` + `release.yml`) if new deps or files are added
- **No PII** — no institutional names, employee names, u-numbers, or internal URLs in tracked files, commits, or PRs

### Code Quality Gates

- **TypeScript:** `strict: true`, no `any`, no `// @ts-ignore`, no `console.log` (use `debugLog`)
- **Python:** type hints on all functions, `mypy --strict`, `ruff` clean, line length ≤ 100
- **Security:** validate all inputs, sanitize outputs, no secrets in code, CORS locked, follow OWASP top 10
- **Tests:** all CI checks must pass — backend (ruff + mypy + pytest) and extension (typecheck + lint + test + build)
- **Tests for every change** — not just happy path. Test edge cases, error states, and the interaction between old and new code.
- **No dead code, no commented-out code, no TODOs.** Ship clean or don't ship.

### Performance Standards

- **No unnecessary work.** Don't poll when nothing is listening. Don't fetch when cached. Don't re-render when props haven't changed.
- **Async by default.** Never block the event loop (backend) or the main thread (frontend). Use `asyncio.gather` for independent I/O, `AbortController` for cancellable requests.
- **Match existing patterns.** Singleton services, Zustand selectors, Radix primitives — if there's an established pattern, use it. Don't invent new ones.

### After Development

- **Run full CI locally** before pushing when possible
- **PR description** must explain what changed and why
- **Clean up** branches after merge, worktrees after PR completion

<!-- ooo:START -->
<!-- ooo:VERSION:0.14.0 -->
# Ouroboros — Specification-First AI Development

> Before telling AI what to build, define what should be built.
> As Socrates asked 2,500 years ago — "What do you truly know?"
> Ouroboros turns that question into an evolutionary AI workflow engine.

Most AI coding fails at the input, not the output. Ouroboros fixes this by
**exposing hidden assumptions before any code is written**.

1. **Socratic Clarity** — Question until ambiguity ≤ 0.2
2. **Ontological Precision** — Solve the root problem, not symptoms
3. **Evolutionary Loops** — Each evaluation cycle feeds back into better specs

```
Interview → Seed → Execute → Evaluate
    ↑                           ↓
    └─── Evolutionary Loop ─────┘
```

## ooo Commands

Each command loads its agent/MCP on-demand. Details in each skill file.

| Command | Loads |
|---------|-------|
| `ooo` | — |
| `ooo interview` | `ouroboros:socratic-interviewer` |
| `ooo seed` | `ouroboros:seed-architect` |
| `ooo run` | MCP required |
| `ooo evolve` | MCP: `evolve_step` |
| `ooo evaluate` | `ouroboros:evaluator` |
| `ooo unstuck` | `ouroboros:{persona}` |
| `ooo status` | MCP: `session_status` |
| `ooo setup` | — |
| `ooo help` | — |

## Agents

Loaded on-demand — not preloaded.

**Core**: socratic-interviewer, ontologist, seed-architect, evaluator,
wonder, reflect, advocate, contrarian, judge
**Support**: hacker, simplifier, researcher, architect
<!-- ooo:END -->
