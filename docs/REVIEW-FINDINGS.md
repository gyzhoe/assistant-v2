# AI Helpdesk Assistant -- Consolidated Code Review Report

**Date:** 2026-03-01
**Reviewers:**
- Boris the Backend Brain (Backend)
- Fiona the Frontend Engineer (Frontend)
- Valentino the Visual Architect (UI/CSS)
- Ursula the UX Strategist (UX)
- Igor the Implementation Inspector (Implementation)

---

## 1. Executive Summary

Five specialists independently reviewed the AI Helpdesk Assistant codebase covering backend Python code, frontend TypeScript/React, CSS/design tokens, UX flows, and cross-cutting implementation concerns (build system, CI, installer, API contracts).

**Overall health:** The codebase is well-structured for a PoC with strong fundamentals -- solid security middleware, consistent ARIA/accessibility, clean design token usage, and good test coverage. However, there are systemic issues around version drift, blocking I/O in async handlers, duplicated code across surfaces, and gaps in the CI/installer pipeline for the management SPA.

**Totals:** 79 findings across all specialists (after deduplication: 68 unique findings). 3 critical, 11 high, 24 medium, 30 low.

---

## 2. Cross-Cutting Themes

### Theme A: Version String Drift
**Flagged by:** Boris, Fiona, Igor

Six locations carry version numbers with four different values (`1.3.0`, `1.4.0`, `1.7.0`, `1.8.0`). The backend config hardcodes `1.7.0` while `pyproject.toml` says `1.8.0`; the frontend `package.json` says `1.4.0` while `manifest.json` says `1.8.0`; the installer defaults to `1.3.0`.

### Theme B: Confirm Dialog Broken in Dark Mode (Radix Portal CSS Vars)
**Flagged by:** Valentino, Fiona, Ursula

The Radix `AlertDialog.Portal` renders outside `.app-shell`, so CSS custom properties are not inherited. Hardcoded fallback values are all light-theme colors. Dark mode users see a jarring white dialog.

### Theme C: Skeleton/CSS Naming Mismatch (`.skeleton-line-85`)
**Flagged by:** Valentino, Fiona

`.skeleton-line-85` sets `width: 83.3333%` instead of 85%.

### Theme D: Duplicated Code Across Surfaces
**Flagged by:** Boris, Fiona, Igor

- Duplicated `_content_id` SHA-256 helper in 3 backend files (Boris)
- Duplicated HTML text extraction logic between `microsoft_docs.py` and `url_loader.py` (Boris)
- Duplicated TypeScript types between `shared/types.ts` and `management/types.ts` (Fiona)
- Duplicated API client between `lib/api-client.ts` and `management/api.ts` (Fiona)
- `DeleteResponse` schema mismatch between frontend type and backend model (Igor)

### Theme E: Silent Error Swallowing
**Flagged by:** Boris, Fiona, Ursula

- Backend feedback endpoint swallows all errors returning 204 (Boris)
- Frontend model selector silently catches fetch errors (Fiona, Ursula)
- Feedback rating failure is silent to the user (Ursula)
- Pin limit reached with no feedback (Ursula)

### Theme F: Blocking I/O in Async Handlers
**Flagged by:** Boris

Multiple sync calls (`chroma_client.list_collections()`, `subprocess.run()`, `time.sleep()`) block the async event loop in health check and ingestion endpoints.

### Theme G: Management SPA Not Built or Bundled
**Flagged by:** Igor

CI does not build the management SPA, the release workflow does not build it, and the installer does not bundle the `backend/static/manage/` directory. Users installing via the installer will not have the KB management UI.

---

## 3. Findings by Priority

### Critical (must fix)

**C1. Version mismatch between config.py and pyproject.toml**
- **Specialists:** Boris (B1), Igor (I1), Fiona (F1)
- **Files:** `backend/app/config.py:19`, `backend/pyproject.toml:4`, `extension/package.json:2`, `extension/public/manifest.json:4`, `installer/setup.iss:3`
- **Problem:** Four different version numbers across six locations. The `/health` endpoint returns stale `1.7.0`. Frontend `package.json` says `1.4.0` while `manifest.json` says `1.8.0`. Installer defaults to `1.3.0`.
- **Fix:** Establish a single source of truth. Use `importlib.metadata.version()` for backend. Add a prebuild script to sync `manifest.json` from `package.json`. Add CI validation that all version strings match.

**C2. Blocking I/O in async health check (ChromaDB calls)**
- **Specialist:** Boris (B2)
- **Files:** `backend/app/routers/health.py:45-49`
- **Problem:** `chroma_client.list_collections()` and `col.count()` are synchronous blocking calls in an async endpoint. Under load, these block the event loop and starve other requests.
- **Fix:** Wrap in `await asyncio.to_thread(...)` as done in other routers.

**C3. Blocking subprocess calls in async handlers (`/ollama/start`, `/ollama/stop`)**
- **Specialist:** Boris (B3)
- **Files:** `backend/app/routers/health.py:87-98`, `backend/app/routers/health.py:105-120`
- **Problem:** `subprocess.Popen()` and `subprocess.run()` block the event loop in async handlers.
- **Fix:** Use `asyncio.create_subprocess_exec()` or wrap in `await asyncio.to_thread(...)`.

---

### High (should fix soon)

**H1. requirements.txt contains massive dependency bloat (langchain)**
- **Specialist:** Igor (I2)
- **Files:** `backend/requirements.txt`, `backend/pyproject.toml`
- **Problem:** `requirements.txt` includes langchain and ~50+ transitive dependencies not declared in `pyproject.toml` and not imported anywhere. Inflates installer by potentially hundreds of MB.
- **Fix:** Regenerate from current `pyproject.toml`: `uv pip compile pyproject.toml -o requirements.txt`. Add CI check.

**H2. Duplicate type definitions between shared and management**
- **Specialist:** Fiona (F2)
- **Files:** `extension/src/shared/types.ts`, `extension/src/management/types.ts`
- **Problem:** `IngestUploadResponse`, `HealthResponse`, `KBArticleListItem` and others are defined independently in both files, risking silent divergence.
- **Fix:** Have `management/types.ts` re-export overlapping types from `shared/types.ts`.

**H3. Duplicate API client between shared and management**
- **Specialist:** Fiona (F3)
- **Files:** `extension/src/lib/api-client.ts`, `extension/src/management/api.ts`
- **Problem:** Two separate API clients with overlapping methods and duplicated `ApiError` classes. Partially intentional (management SPA lacks `chrome.storage`).
- **Fix:** Extract shared `fetchApi` helper that accepts a token-provider function. Document the design decision.

**H4. Module-level `asyncio.Semaphore` uses private `._value` attribute**
- **Specialist:** Boris (B4)
- **Files:** `backend/app/routers/shared.py:6`, `backend/app/routers/ingest.py:60,169`, `backend/app/routers/kb.py:218,337`
- **Problem:** `upload_semaphore._value` is a private attribute that could break across Python versions.
- **Fix:** Replace with `upload_semaphore.locked()` (public API).

**H5. Race condition in semaphore pre-check (TOCTOU)**
- **Specialist:** Boris (B5)
- **Files:** `backend/app/routers/ingest.py:60-66`, `backend/app/routers/kb.py:218-224`
- **Problem:** Between checking `_value` and entering `async with`, another request could acquire the semaphore.
- **Fix:** Use `upload_semaphore.acquire_nowait()` with try/except ValueError pattern.

**H6. Feedback endpoint silently swallows all errors**
- **Specialist:** Boris (B6)
- **Files:** `backend/app/routers/feedback.py:57-58`
- **Problem:** Bare `except Exception` returns 204 regardless. Embedding failures, ChromaDB corruption, and programming bugs are all silently lost.
- **Fix:** Distinguish expected from unexpected errors. Return 503 for Ollama failures.

**H7. New httpx.Client created per request in services**
- **Specialist:** Boris (B7)
- **Files:** `backend/app/services/embed_service.py:52`, `backend/app/services/llm_service.py:43`, `backend/app/services/microsoft_docs.py:120,150`
- **Problem:** Every embed/generate/search call creates and tears down a new TCP connection pool. No HTTP connection reuse.
- **Fix:** Use a module-level or class-level `httpx.Client` that persists across requests.

**H8. MutationObserver watches entire document.body with subtree**
- **Specialist:** Fiona (F4)
- **Files:** `extension/src/content/sidebar-host.ts:47-50`
- **Problem:** Observes `document.body` with `{ childList: true, subtree: true }` firing hundreds of mutations on complex WHD pages. `SidebarHost.stop()` is never called.
- **Fix:** Observe a more targeted container (e.g., `#ticketDetailForm`). Add `characterData: false, attributes: false`.

**H9. `useSettings` hook creates multiple independent copies**
- **Specialist:** Fiona (F5, F7)
- **Files:** `extension/src/sidebar/hooks/useSettings.ts`, `extension/src/sidebar/hooks/useTheme.ts:21`
- **Problem:** Each call to `useSettings()` creates independent `useState` copies. Settings changes in one consumer are invisible to others until remount.
- **Fix:** Move settings into the Zustand store or a shared React context.

**H10. Confirm dialog broken in dark mode**
- **Specialists:** Valentino (V6), Fiona (F15), Ursula (U7)
- **Files:** `extension/src/management/management.css:1145-1230`
- **Problem:** Radix Portal renders outside `.app-shell`, hardcoded fallbacks are all light-theme colors. Dark mode users see a white dialog.
- **Fix:** Set CSS custom properties on `:root` or `body` instead of `.app-shell`, or use Radix's `container` prop to render inside `.app-shell`.

**H11. Options page has no unsaved changes warning**
- **Specialist:** Ursula (U4)
- **Files:** `extension/src/options/OptionsPage.tsx`
- **Problem:** No dirty-state tracking or `beforeunload` protection. Unlike the ArticleEditor (which has `isDirty` + `ConfirmDialog`), the options page silently discards changes on navigation.
- **Fix:** Track dirty state, show "Unsaved changes" indicator, add `beforeunload` listener.

---

### Medium (plan to fix)

**M1. `_cleanup_temp` uses blocking `time.sleep` in async context**
- **Specialist:** Boris (B8)
- **Files:** `backend/app/routers/ingest.py:307`
- **Problem:** Blocks the event loop for up to 1.5s (3 retries x 0.5s).
- **Fix:** Make async with `await asyncio.sleep(delay)` or use `asyncio.to_thread()`.

**M2. Article cache not thread-safe**
- **Specialist:** Boris (B9)
- **Files:** `backend/app/routers/kb.py:50-62`, `backend/app/routers/kb.py:114-140`
- **Problem:** Module-level globals mutated without locking by concurrent requests.
- **Fix:** Use `asyncio.Lock` or accept the race as benign (worst case: redundant cache rebuild).

**M3. Microsoft Docs cache not thread-safe**
- **Specialist:** Boris (B10)
- **Files:** `backend/app/services/microsoft_docs.py:38-62`
- **Problem:** Dict mutations from `asyncio.to_thread` workers without locking.
- **Fix:** Use `threading.Lock` since cache is accessed from thread pool workers.

**M4. `article_id` collision risk for manual articles**
- **Specialist:** Boris (B11)
- **Files:** `backend/app/routers/kb.py:194-196`
- **Problem:** SHA-256 truncated to 16 hex chars (64 bits). Low risk at current scale but undocumented.
- **Fix:** Document the truncation. Consider adding UUID/timestamp for future scale.

**M5. `update_article` deletes chunks before re-creating (non-atomic)**
- **Specialist:** Boris (B12)
- **Files:** `backend/app/routers/kb.py:348-380`
- **Problem:** If embedding fails between delete and upsert, the article is permanently lost.
- **Fix:** Upsert new chunks first with version suffix, then delete old chunks.

**M6. Rate limiter ineffective behind reverse proxy**
- **Specialist:** Boris (B13)
- **Files:** `backend/app/middleware/security.py:123`
- **Problem:** Uses `request.client.host` which is the proxy IP behind a reverse proxy.
- **Fix:** Document that rate limiting assumes direct connections. Add proxy-aware IP extraction if deployed remotely.

**M7. `/manage` static file mount has no auth protection**
- **Specialist:** Boris (B14)
- **Files:** `backend/app/main.py:92-98`
- **Problem:** The KB management SPA bypasses API auth middleware. Anyone reaching the backend can access the management UI.
- **Fix:** For local deployment this is acceptable. Document the limitation for network exposure.

**M8. API contract says `ticket_subject`/`ticket_description` required, backend defaults them**
- **Specialist:** Igor (I3)
- **Files:** `docs/api-contract.md:58-60`, `backend/app/models/request_models.py:14-19`
- **Problem:** Contract says required, Pydantic model has `default=""` making them optional.
- **Fix:** Remove defaults to make truly required, or update contract to say optional.

**M9. Default model mismatch in API contract**
- **Specialist:** Igor (I4)
- **Files:** `docs/api-contract.md:65`, `backend/app/models/request_models.py:23`
- **Problem:** Contract says `llama3.2:3b`, code uses `qwen2.5:14b`.
- **Fix:** Update contract. Consider reading default from `settings.default_model`.

**M10. API contract missing 12+ endpoints**
- **Specialist:** Igor (I5)
- **Files:** `docs/api-contract.md`
- **Problem:** Only 5 of 17+ endpoints are documented. All KB management, feedback, and lifecycle endpoints are missing.
- **Fix:** Add documentation for missing endpoints.

**M11. `shutdown`/`ollamaStart`/`ollamaStop` API client missing auth headers**
- **Specialist:** Igor (I7)
- **Files:** `extension/src/lib/api-client.ts:55-72`
- **Problem:** These methods do not call `buildHeaders()`. With `API_TOKEN` configured, calls fail with 401.
- **Fix:** Add `buildHeaders()` call to all three methods.

**M12. Missing `uv.lock` file in repository**
- **Specialist:** Igor (I9)
- **Files:** `backend/` (no `uv.lock`)
- **Problem:** `uv sync` resolves different versions on different machines. Non-reproducible builds.
- **Fix:** Run `uv lock` and commit the resulting file.

**M13. CI and release workflows skip management SPA build**
- **Specialist:** Igor (I10)
- **Files:** `.github/workflows/ci.yml:38`, `.github/workflows/release.yml:26`
- **Problem:** Management SPA build errors are never caught by CI. Release installer omits a fresh management build.
- **Fix:** Add `npm run build:management --workspace=extension` to both workflows.

**M14. Installer missing management SPA static assets**
- **Specialist:** Igor (I11)
- **Files:** `installer/setup.iss:55-78`
- **Problem:** `backend/static/manage/` is not bundled. Installer users have no KB management UI.
- **Fix:** Add `backend/static/` to the installer `[Files]` section.

**M15. Inconsistent token sets across CSS surfaces**
- **Specialist:** Valentino (V4)
- **Files:** `sidebar.css:19-88`, `options.css:17-55`, `management.css:21-90`
- **Problem:** Options page has unique tokens (`--surface-hover`, `--input-bg`, etc.), management has others (`--surface-active`, `--overlay-bg`). `--danger-fg` defined but never used.
- **Fix:** Establish a shared token reference. Remove unused `--danger-fg`.

**M16. Transition duration inconsistency (150ms vs 120ms)**
- **Specialist:** Valentino (V5)
- **Files:** `options.css:128,205,233,266,283`
- **Problem:** Options page uses `0.15s ease` (150ms) while sidebar and management use `120ms ease` per the design spec.
- **Fix:** Replace all `0.15s` with `120ms` in `options.css` (~8 occurrences).

**M17. `BackendControl` start/stop buttons have no double-click guard**
- **Specialist:** Fiona (F6)
- **Files:** `extension/src/sidebar/components/BackendControl.tsx:79-108`
- **Problem:** Rapid clicks create multiple shutdown requests and timers. Transitional states (`stopping`/`starting`) not used to disable buttons.
- **Fix:** Disable buttons during transitional states.

**M18. `handleDelete` in ArticleList has unmount race condition**
- **Specialist:** Fiona (F16)
- **Files:** `extension/src/management/components/ArticleList.tsx:54-82`
- **Problem:** The 3-second `setTimeout` for deferred deletion is not cleared on unmount, potentially executing after component is gone.
- **Fix:** Store timeout in a `useRef` and clear on unmount via `useEffect` cleanup.

**M19. Silent failure when pinning article at max limit**
- **Specialist:** Ursula (U1)
- **Files:** `extension/src/sidebar/store/sidebarStore.ts:62-64`
- **Problem:** `pinArticle` silently returns at 10 items. No user feedback. Button stays enabled.
- **Fix:** Disable button at limit and show "(10/10 max)" label, or flash a warning message.

**M20. Feedback rating failure is silent**
- **Specialist:** Ursula (U2)
- **Files:** `extension/src/sidebar/hooks/useSubmitFeedback.ts:24-27`
- **Problem:** Catch block resets rating to null with no error message in production.
- **Fix:** Show inline error "Could not save rating. Try again."

**M21. No save feedback differentiation (success vs failure)**
- **Specialist:** Ursula (U5)
- **Files:** `extension/src/options/OptionsPage.tsx:65-67`
- **Problem:** Success and failure messages use the same muted gray style. Errors are easy to miss.
- **Fix:** Use green/checkmark for success, red/error color for failure.

**M22. Model selector silently falls back when backend is offline**
- **Specialists:** Fiona (F12), Ursula (U6)
- **Files:** `extension/src/sidebar/components/ModelSelector.tsx:12-16`
- **Problem:** `.catch(() => {})` swallows error. Shows default model with no indication fetch failed.
- **Fix:** Show hint "(could not fetch models)" or add refresh button. Re-fetch on backend status change.

**M23. No network/offline error detection in sidebar**
- **Specialist:** Ursula (U10)
- **Files:** `extension/src/sidebar/hooks/useGenerateReply.ts:49-63`
- **Problem:** `TypeError: Failed to fetch` falls through to generic error. No indication the problem is network connectivity.
- **Fix:** Check for `TypeError` with `fetch` in message and show "Network error. Check your connection."

**M24. Upload error halts batch with no option to continue**
- **Specialist:** Ursula (U11)
- **Files:** `extension/src/sidebar/hooks/useKnowledgeImport.ts:128-156`
- **Problem:** One file failure stops the entire batch. Retry re-uploads all files including successful ones.
- **Fix:** Show partial progress, offer "Skip & Continue", only retry failed files.

**M25. Undo window for article deletion is only 3 seconds**
- **Specialist:** Ursula (U12)
- **Files:** `extension/src/management/components/ArticleList.tsx:71-73`, `extension/src/management/components/Toast.tsx:25`
- **Problem:** 3-second undo window for a destructive operation is too short.
- **Fix:** Extend to 8-10 seconds. Keep toast visible for full duration.

**M26. No first-time onboarding flow**
- **Specialist:** Ursula (U20)
- **Files:** `extension/src/sidebar/components/BackendControl.tsx:144-162`
- **Problem:** First-time users see all readiness badges failing with no guidance on what to do.
- **Fix:** Show onboarding card with ordered steps when all checks fail. Make badges clickable.

---

### Low (nice to have)

| # | Finding | Specialist | Key File(s) |
|---|---------|-----------|-------------|
| L1 | Orphaned `.app-header` CSS selector (dead code) | Valentino | `sidebar.css:91-98` |
| L2 | `.import-section-label` class used but no CSS rule | Valentino | `ImportSection.tsx:94` |
| L3 | `.skeleton-line-85` sets 83.3% width, not 85% | Valentino, Fiona | `sidebar.css:692` |
| L4 | Tailwind `font-mono` diverges from CSS design tokens | Valentino | `tailwind.config.ts` |
| L5 | Single `!important` -- use natural specificity | Valentino | `management.css:843` |
| L6 | `httpx` import in `pipeline.py` conditionally used | Boris | `pipeline.py:12` |
| L7 | `chunk_by_paragraphs` dead code | Boris | `chunker.py:30-58` |
| L8 | `_content_id` helper duplicated in 3 files | Boris | `kb_loader.py:22`, `ticket_loader.py:28`, `url_loader.py:186` |
| L9 | HTML text extraction duplicated | Boris | `microsoft_docs.py:168`, `url_loader.py:161` |
| L10 | Test coverage gaps (6+ untested paths) | Boris | Various |
| L11 | `clear_collection` returns 422, contract says 404 | Igor | `ingest.py:141` vs `api-contract.md:188` |
| L12 | `DeleteResponse` schema mismatch (frontend/backend) | Igor | `management/types.ts:41-44` |
| L13 | `BaseHTTPMiddleware` perf (known deferred) | Igor, Boris | `security.py` |
| L14 | Vite 7 / Vitest 2 compat unverified | Igor | `extension/package.json:49-50` |
| L15 | Installer hardcoded component index | Igor | `setup.iss:243-246` |
| L16 | Auth token sent to exempt `/health` endpoint | Igor | `management/api.ts:104-106` |
| L17 | Token in `sessionStorage` (ok for local PoC) | Fiona | `management/api.ts:31-32` |
| L18 | Stable Zustand setters in dep array (style) | Fiona | `useGenerateReply.ts:69` |
| L19 | `searchKBArticles` always returns page 1 | Fiona | `api-client.ts:128-129` |
| L20 | `DOMReader` re-created per message | Fiona | `content/index.ts:40-41` |
| L21 | `sr-only` class may be tree-shaken | Fiona | `InsertButton.tsx:72` |
| L22 | Tab panels missing `aria-labelledby` | Fiona | `KnowledgePanel.tsx:102-109` |
| L23 | No `aria-busy` during article list refetch | Fiona | `ArticleList.tsx:127-128` |
| L24 | Unused `React` imports (JSX auto-runtime) | Fiona | Multiple sidebar files |
| L25 | `SidebarHost.stop()` never called | Fiona | `sidebar-host.ts:19-27` |
| L26 | `handleChange` accepts `string` for all fields | Fiona | `OptionsPage.tsx:35-37` |
| L27 | E2E tests are stubs | Fiona | `sidebar.spec.ts` |
| L28 | Management `ApiError` missing `readonly` | Fiona | `management/api.ts:19-20` |
| L29 | Unnecessary `useMemo` in BackendControl | Fiona | `BackendControl.tsx:144-149` |
| L30 | No generation time estimate/timer | Ursula | `SkeletonLoader.tsx` |
| L31 | TokenGate description hidden by `display: none` | Ursula | `management.css:982-984` |
| L32 | Settings gear shows toast, not navigation | Ursula | `Header.tsx:69-78` |
| L33 | ErrorBoundary has no retry button | Ursula | `ErrorBoundary.tsx` |
| L34 | No ticket description preview in sidebar | Ursula | `TicketContext.tsx` |
| L35 | No client-side URL validation before import | Ursula | `ImportTab.tsx:30-54` |
| L36 | No client-side file size check in sidebar import | Ursula | `useKnowledgeImport.ts:64-95` |
| L37 | Keyboard shortcut not discoverable | Ursula | `ReplyPanel.tsx:99` |
| L38 | Insert button label ambiguous (targets Tech Notes) | Ursula | `InsertButton.tsx:59` |
| L39 | Success auto-dismiss loses upload warnings | Ursula | `useKnowledgeImport.ts:164-167` |

---

## 4. Quick Wins

Items that are trivial to fix (< 30 minutes each):

| # | Finding | Effort | Ref |
|---|---------|--------|-----|
| 1 | Update `config.py` version to `1.8.0` | 1 min | C1 |
| 2 | Update `package.json` versions to `1.8.0` | 2 min | C1 |
| 3 | Delete `.app-header` CSS block (8 lines) | 1 min | L1 |
| 4 | Rename `.skeleton-line-85` to `.skeleton-line-83` or fix width | 2 min | L3 |
| 5 | Replace `upload_semaphore._value` with `.locked()` (4 locations) | 10 min | H4 |
| 6 | Remove `chunk_by_paragraphs` dead code | 2 min | L7 |
| 7 | Replace `0.15s` with `120ms` in options.css (~8 occurrences) | 5 min | M16 |
| 8 | Add `readonly` to management `ApiError` properties | 1 min | L28 |
| 9 | Remove unused `--danger-fg` token from options.css | 1 min | M15 |
| 10 | Fix `DeleteResponse` type to use `article_id` instead of `status` | 2 min | L12 |
| 11 | Update API contract default model to `qwen2.5:14b` | 1 min | M9 |
| 12 | Update `clear_collection` status code or contract | 2 min | L11 |
| 13 | Remove unnecessary `useMemo` in BackendControl | 2 min | L29 |
| 14 | Remove single `!important` in management.css | 2 min | L5 |
| 15 | Add `buildHeaders()` to shutdown/ollamaStart/ollamaStop | 5 min | M11 |
| 16 | Wrap ChromaDB calls in `asyncio.to_thread()` in health.py | 10 min | C2 |
| 17 | Change `time.sleep` to `asyncio.sleep` in `_cleanup_temp` | 5 min | M1 |
| 18 | Show description text in TokenGate (remove `display: none`) | 1 min | L31 |
| 19 | Update insert button label to "Insert into Tech Notes" | 1 min | L38 |
| 20 | Extend undo timeout from 3s to 8-10s | 2 min | M25 |

---

## 5. Larger Efforts

Items requiring design decisions or significant refactoring:

| # | Finding | Effort Estimate | Ref |
|---|---------|-----------------|-----|
| 1 | Establish single version source of truth with CI validation | 1-2 days | C1 |
| 2 | Regenerate requirements.txt and add CI staleness check | 2-4 hours | H1 |
| 3 | Consolidate duplicate types and API client across surfaces | 1-2 days | H2, H3 |
| 4 | Fix Radix Portal dark mode (requires CSS architecture decision) | 4-8 hours | H10 |
| 5 | Move settings into Zustand store (shared state refactor) | 4-8 hours | H9 |
| 6 | Add management SPA to CI, release, and installer pipelines | 4-8 hours | M13, M14 |
| 7 | Implement persistent httpx.Client in services | 4-8 hours | H7 |
| 8 | Make `update_article` atomic (upsert-then-delete pattern) | 4-8 hours | M5 |
| 9 | Narrow MutationObserver scope and add cleanup | 2-4 hours | H8 |
| 10 | Document all 17+ API endpoints in contract | 1-2 days | M10 |
| 11 | Add unsaved changes warning to Options page | 2-4 hours | H11 |
| 12 | Implement upload batch error recovery (skip & continue) | 4-8 hours | M24 |
| 13 | First-time onboarding flow | 1-2 days | M26 |
| 14 | Add thread-safety to caches (asyncio.Lock / threading.Lock) | 2-4 hours | M2, M3 |
| 15 | Fill test coverage gaps | 2-3 days | L10, L27 |
| 16 | Rewrite BaseHTTPMiddleware as pure ASGI (pre-production) | 2-3 days | L13 |

---

## 6. Statistics

### Findings Per Specialist

| Specialist | Role | Findings | Critical | High | Medium | Low |
|-----------|------|----------|----------|------|--------|-----|
| Boris | Backend | 19 | 3 | 4 | 7 | 5 |
| Fiona | Frontend | 27 | 3 | 5 | 10 | 9 |
| Valentino | UI/CSS | 8 | 0 | 0 | 2 | 6 |
| Igor | Implementation | 15 | 0 | 2 | 6 | 7 |
| Ursula | UX | 20 | 0 | 2 | 8 | 10 |
| **Total (raw)** | | **89** | **6** | **13** | **33** | **37** |

### After Deduplication

| Severity | Count |
|----------|-------|
| Critical | 3 |
| High | 11 |
| Medium | 26 |
| Low | 39 |
| **Total** | **79** |

*Note: 10 findings were flagged by multiple specialists and deduplicated (credited to all who found them).*

### Findings by Category

| Category | Count |
|----------|-------|
| Performance / Blocking I/O | 6 |
| Configuration / Version drift | 5 |
| Code duplication | 6 |
| API contract alignment | 6 |
| Concurrency / Thread safety | 4 |
| Error handling / Silent failures | 6 |
| CSS organization / Dead CSS | 6 |
| User feedback / UX | 9 |
| Build / CI / Installer | 5 |
| Security | 4 |
| Accessibility | 4 |
| React patterns / State management | 6 |
| Dependency management | 3 |
| Testing | 3 |
| Discoverability / Onboarding | 5 |
| Data integrity | 2 |

---

*Report compiled from specialist reviews dated 2026-03-01.*
