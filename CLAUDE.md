# CLAUDE.md — AI Helpdesk Assistant

This file defines the working rules for all Claude agents on this project.
It is loaded automatically at the start of every session.

---

## Project Overview

Local AI assistant for SolarWinds Web Help Desk (on-prem). Delivered as a Microsoft Edge
browser extension (Manifest V3) with a Python FastAPI backend. All AI inference is local
via Ollama — no cloud calls are ever made.

**Repo:** `C:\Playground\git\assistant`
**Plan:** `C:\Users\Alen_\.claude\plans\unified-kindling-patterson.md`
**Team:** `C:\Users\Alen_\.claude\projects\C--Playground\memory\agent-team.md`

---

## Session Startup — MANDATORY FIRST STEP

At the start of every session the **Manager agent** must:

1. Call `TaskList` to see all task statuses
2. Identify any `in_progress` tasks and resume or reassign them
3. Identify the next unblocked `pending` tasks and assign specialist agents
4. Each agent must call `TaskUpdate { status: "in_progress", owner: "<role>" }` before starting
5. Each agent must call `TaskUpdate { status: "completed" }` immediately after finishing

**Never start writing code without first checking the task list.**
This ensures sessions can be resumed cleanly across conversations.

---

## Agent Team

| Role | Model | Leads |
|---|---|---|
| Manager | `claude-sonnet-4-6` | Orchestration, best-practice enforcement |
| App Designer | `claude-sonnet-4-6` | Architecture, API contracts |
| UX Specialist | `claude-haiku-4-5-20251001` | Flows, accessibility, usability |
| UI Specialist | `claude-haiku-4-5-20251001` | Components, Tailwind, Radix, Fluent Design |
| Dev Frontend | `claude-sonnet-4-6` | TypeScript, React, MV3 extension |
| Dev Backend | `claude-sonnet-4-6` | Python, FastAPI, ingestion CLI |
| AI Implementation Specialist | `claude-sonnet-4-6` | Ollama, LangChain, RAG, ChromaDB |
| Tester | `claude-haiku-4-5-20251001` | Vitest, pytest, Playwright |
| Reviewer | `claude-sonnet-4-6` | Code review, security, quality gate |

Full definitions: `C:\Users\Alen_\.claude\projects\C--Playground\memory\agent-team.md`

---

## GitHub Best Practices

- **Branch strategy:** feature branches off `main`; naming: `feat/phase-N-<slug>`, `fix/`, `chore/`, `docs/`
- **Commit style:** Conventional Commits — `feat(extension): add sidebar panel`, `fix(backend): handle Ollama timeout`
- **PRs:** All PRs require the Reviewer agent sign-off + CI green before merge
- **No force-push to main** — ever
- **PR template** at `.github/PULL_REQUEST_TEMPLATE.md` must be completed
- **Issue templates** for bug reports and feature requests
- **Dependabot** runs weekly for both npm and pip dependencies
- **Releases:** Semantic versioning (`v1.0.0`); release pipeline zips extension and attaches to GitHub Release

## Git Worktrees — REQUIRED for parallel agent work

Worktrees allow multiple agents to work on separate branches simultaneously without
interfering. All feature work happens in worktrees — never directly on `main`.

**Worktree root:** `C:\Playground\git\assistant-worktrees\`

### Lifecycle (per task/phase)

```bash
# 1. Manager creates branch + worktree when task starts
git worktree add ..\assistant-worktrees\phase-1-backend feat/phase-1-backend

# 2. Agent works exclusively inside that worktree directory
#    cd C:\Playground\git\assistant-worktrees\phase-1-backend

# 3. Agent commits with conventional commit messages
git add <files>
git commit -m "feat(backend): add FastAPI health endpoint"

# 4. Agent pushes and opens PR
git push -u origin feat/phase-1-backend
gh pr create --title "feat(backend): phase 1 backend skeleton" --body "..."

# 5. Reviewer reviews; Manager merges via GitHub (squash merge preferred)

# 6. Manager removes worktree after merge
git worktree remove ..\assistant-worktrees\phase-1-backend
git branch -d feat/phase-1-backend
```

### Rules
- One worktree per active task/phase — never share a worktree between agents
- `main` worktree (`C:\Playground\git\assistant`) is always clean — only Manager touches it for merge/tag operations
- Worktree directories are sibling to the repo root: `C:\Playground\git\assistant-worktrees\<branch>`
- Always `git worktree list` before creating a new one to avoid conflicts
- Worktrees are ephemeral — create on task start, remove after PR merge
- Agents that can run in parallel (e.g. Phase 1 backend + Phase 2 extension) each get their own worktree simultaneously

### Parallel worktree map (phases that can coexist)
| Worktree | Branch | Agent |
|---|---|---|
| `phase-1-backend` | `feat/phase-1-backend` | Dev Backend |
| `phase-2-extension` | `feat/phase-2-extension` | Dev Frontend + UI Specialist |
| `phase-3-dom` | `feat/phase-3-dom` | Dev Frontend |
| `phase-4-rag` | `feat/phase-4-rag` | AI Specialist |
| `phase-7-options` | `feat/phase-7-options` | UI Specialist |

---

## Coding Best Practices

### TypeScript / Extension
- `strict: true` in `tsconfig.json` — no `any`, no `// @ts-ignore`
- No `console.log` in production code — use a debug utility gated on `process.env.NODE_ENV`
- All chrome.runtime messages typed via the discriminated union in `src/shared/messages.ts`
- DOM selectors stored in `chrome.storage.sync` as `selectorOverrides` — never hardcoded strings scattered across files
- `dom-inserter.ts` must use the native setter trick — never `textarea.value = x` directly
- MutationObserver always debounced (≥ 300ms) to prevent message floods

### Python / Backend
- Python 3.11+, type hints on all functions and classes
- `pydantic-settings` for all config — no raw `os.environ` calls
- CORS origin locked to `chrome-extension://<ID>` — never `"*"` in production
- No secrets or credentials committed — use `.env` files (`.gitignored`)
- All async routes use `async def`; blocking Ollama/ChromaDB calls wrapped with `asyncio.to_thread` where needed
- `ruff` for linting, `mypy` for type checking — both must pass in CI

### General
- No over-engineering: build the minimum needed for the current phase
- No backwards-compatibility shims — if something is removed, remove it completely
- Comments only where logic is non-obvious
- New logic always accompanied by tests before the task is marked `completed`

---

## UX & Design Best Practices

- **Design system:** Fluent Design aesthetic — accent blue `#0078d4`, neutral grays
- **Component library:** Radix UI primitives + Tailwind CSS
- **Non-blocking:** sidebar never obscures ticket content
- **States required for every interactive element:** default, loading, success, error, disabled
- **Accessibility targets:** Lighthouse score ≥ 90; all elements keyboard-navigable; ARIA labels on all icon buttons; `aria-live` regions for dynamic content
- **Keyboard shortcut:** `Alt+Shift+H` toggles sidebar
- Skeleton loaders (not spinners) for generation wait states
- Error messages must tell the user what to do next — not just what went wrong

---

## Security Rules

- CORS restricted to the exact extension origin — verified in `config.py`
- No API keys, tokens, or passwords in any committed file
- Content script uses `MutationObserver` — never `eval()` or `innerHTML` with untrusted content
- Backend validates all request fields via Pydantic — no raw dict access
- Extension `host_permissions` minimal: only `http://localhost:8765/*`

---

## Testing Requirements

- Every new function/hook/service must have a corresponding unit test
- PRs without tests for new logic will be rejected by the Reviewer
- Extension unit tests: `npx vitest run`
- Backend tests: `uv run pytest backend/tests/ -v`
- E2E tests: `npx playwright test`
- CI must be green on all three before merge to `main`

---

## File Structure Reference

```
assistant/
├── extension/          TypeScript + React 18 + Vite + MV3
│   ├── src/background/ Service worker (message relay)
│   ├── src/content/    DOM reader + inserter + MutationObserver
│   ├── src/sidebar/    React UI + hooks + Zustand store
│   ├── src/options/    Settings page
│   └── src/shared/     types.ts, messages.ts, constants.ts
├── backend/            Python FastAPI
│   ├── app/routers/    generate, health, models, ingest
│   ├── app/services/   llm_service, rag_service, embed_service
│   └── ingestion/      CLI + loaders + pipeline
├── docs/               architecture.md, api-contract.md, whd-dom-selectors.md
├── scripts/            dev-setup.sh
└── .github/            CI workflows, templates, dependabot
```
