# Sprint 5: Production Hardening — COMPLETED (2026-03-02)

**Goal:** Fix all critical/high findings from the performance, security, and UX reviews to make the app production-ready for multi-user deployment.

**Scope:** Fixes and hardening only — no new features.

**Result:** 4 PRs merged (#32-#35), 65 files changed, +3,428 / -1,042 lines, 516+ tests passing.

---

## Track A: Backend Performance (Large — Lead + Junior)

**Branch:** `fix/backend-perf`

The single highest-impact change is refactoring services to singletons with shared async HTTP clients. This addresses 5 findings in one refactor.

| # | Finding | Severity | Files | Description |
|---|---------|----------|-------|-------------|
| A1 | C1+C2+I3+I10 | CRITICAL | `services/*.py`, `routers/generate.py`, `routers/health.py`, `routers/models.py` | **Singleton services with async httpx.** Create `LLMService`, `EmbedService`, `MicrosoftDocsService` once in app lifespan, store on `app.state`. Replace sync `httpx.Client` + `to_thread` with `httpx.AsyncClient`. Share one Ollama client with connection pooling (`max_connections=10`). |
| A2 | C3 | HIGH | `middleware/security.py` | **Rate limiter lock contention.** Replace single global `asyncio.Lock` with per-path-IP keyed approach or lock-free sliding window. Move stale entry sweep to a background task instead of inline. |
| A3 | C4 | HIGH | `routers/kb.py` | **KB article index blocking reload.** Background cache refresh that doesn't block request handling. Serve stale cache while rebuilding. Incremental updates after mutations. |
| A4 | I7 | MEDIUM | `routers/generate.py:255-269` | **Parallel pinned article fetching.** Replace sequential loop with `asyncio.gather` or single ChromaDB `$in` query. |
| A5 | I1+I2 | MEDIUM | `ingestion/pipeline.py` | **Batch embedding in ingestion.** Parallelize chunk embedding with concurrency limit. Fix fallback `_embed` to reuse client. |

**Tests:** Update all affected test files. Expect ~20 test modifications.

**Lead tasks:** A1 (complex async rewrite), A2, A3
**Junior tasks:** A4, A5, test updates

---

## Track B: Backend Security (Medium — Lead + Junior)

**Branch:** `fix/backend-security`

| # | Finding | Severity | Files | Description |
|---|---------|----------|-------|-------------|
| B1 | H2 | HIGH | `routers/auth.py` | **Session persistence.** Replace in-memory `SessionStore` with SQLite-backed store. Add `SESSION_BACKEND=memory\|sqlite` config. Sessions survive restarts. |
| B2 | M1 | MEDIUM | `routers/auth.py`, `middleware/security.py` | **CSRF token.** Add double-submit cookie CSRF protection to state-changing POST/PUT/DELETE endpoints used by management SPA. |
| B3 | M3 | MEDIUM | `routers/health.py` | **Health endpoint scoping.** Return minimal `{"status": "ok"}` for unauthenticated callers. Detailed info (version, collections, counts) behind auth only. |
| B4 | M4 | MEDIUM | `routers/health.py` | **Localhost-only process control.** Restrict `/shutdown`, `/ollama/start`, `/ollama/stop` to connections from `127.0.0.1` (check `scope["client"][0]`). |
| B5 | H3 | MEDIUM | `routers/generate.py` | **Prompt injection delimiters.** Wrap user-supplied content (subject, description, notes) in XML delimiter tags in `_build_prompt()`. |
| B6 | M6+M7 | LOW-MED | `routers/kb.py`, `routers/feedback.py` | **Path param validation.** Add regex validators for `article_id` and `feedback_id` path parameters. |
| B7 | M8 | LOW | `services/microsoft_docs.py` | **MD5 → SHA256** for cache key generation. Eliminates security scanner noise. |
| B8 | L5 | LOW | `config.py`, `package.json` | **Version alignment.** Sync all version strings to `1.11.0`. |

**Lead tasks:** B1, B2, B5
**Junior tasks:** B3, B4, B6, B7, B8

---

## Track C: Frontend Fixes (Large — Lead + Junior)

**Branch:** `fix/frontend-ux`

| # | Finding | Severity | Files | Description |
|---|---------|----------|-------|-------------|
| C1 | UX-C2 | CRITICAL | `ReplyPanel.tsx` | **Copy to clipboard button.** Add clipboard icon button in draft header next to Edit/Preview. `navigator.clipboard.writeText(reply)` + brief "Copied" confirmation. |
| C2 | UX-C1 | CRITICAL | `ReplyPanel.tsx`, `useGenerateReply.ts` | **Generate & Insert shortcut.** Add split-button or toggle: "Generate & Insert" that auto-inserts after successful generation. Store preference in settings. |
| C3 | UX-C3 | CRITICAL | `sidebarStore.ts`, new persist middleware | **Reply persistence.** Persist last reply per ticket URL in `chrome.storage.session`. Restore on navigation back. Use `zustand/middleware` persist adapter. |
| C4 | UX-C5 | HIGH | `dom-inserter.ts`, `OptionsPage.tsx`, `shared/constants.ts` | **Configurable insert target.** Add insert selector override in Options (alongside existing reader overrides). Fall back to defaults. Show helpful error when insert target not found. |
| C5 | Perf-I5 | MEDIUM | `BackendControl.tsx` | **Health poll backoff.** Exponential backoff when offline: 5s → 15s → 30s → 60s. Reset to 5s on reconnect. |
| C6 | UX-P10 | MEDIUM | New `Toast.tsx` in sidebar | **Unified toast system.** Port management SPA toast pattern to sidebar. Replace scattered inline success/error messages. |
| C7 | UX-P6 | LOW | `ManageTab.tsx`, `ImportTab.tsx`, `InsertButton.tsx` | **Success message timing.** Increase auto-dismiss: Insert 2s→4s, ManageTab 3s→5s. Or use toast system from C6. |
| C8 | UX-P4 | LOW | `BackendControl.tsx`, `sidebar.css` | **Settings button style.** Differentiate gear icon from theme toggle visually. |
| C9 | A1+A2+A3 | LOW | `App.tsx`, `KnowledgePanel.tsx`, `sidebar.css` | **Accessibility fixes.** Add `aria-label` on sidebar `<main>`, `aria-orientation` on tablist, darken muted text color for contrast. |

**Lead tasks:** C2, C3, C4
**Junior tasks:** C1, C5, C6, C7, C8, C9

---

## Track D: Docs (Small — Haiku solo)

**Branch:** `docs/sprint-5-changelog`

- Update `CHANGELOG.md` with all Sprint 5 changes
- Merge LAST (after all other tracks)

---

## Merge Order

1. **Track A** (backend perf) — no dependencies
2. **Track B** (backend security) — no dependency on A, can merge in parallel if no file conflicts
3. **Track C** (frontend) — no backend dependency (frontend changes are independent)
4. **Track D** (docs) — merges LAST after A+B+C

Tracks A, B, and C can run in parallel. Each track gets its own worktree.

---

## Team Structure

| Role | Agent | Model | Track |
|------|-------|-------|-------|
| Backend Perf Lead | Sergei Asyncovich | Opus | Track A |
| Backend Perf Junior | Milo Threadkiller | Sonnet | Track A |
| Backend Security Lead | Katrina Locksmith | Opus | Track B |
| Backend Security Junior | Ravi Patchwell | Sonnet | Track B |
| Frontend Lead | Astrid Pixelburn | Opus | Track C |
| Frontend Junior | Lenny Toastmaker | Sonnet | Track C |
| Docs | Hugo Changelogger | Haiku | Track D |

---

## Verification

Each track must pass before merge:
- Backend: `ruff check .` + `mypy app/ ingestion/` + `pytest tests/ -v`
- Extension: `typecheck` + `lint` + `vitest run`
- No regressions in existing test counts (~284 backend, ~151 extension)
