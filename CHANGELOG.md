# Changelog

All notable changes to AI Helpdesk Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.14.0] — Installer Overhaul & Ollama Fixes (2026-03-03)

### Fixed

- Installer directory double-nesting — added `AppendDefaultDirName=no` to prevent Inno Setup from appending `AIHelpdeskAssistant` when the user browses to a folder already containing it
- Ollama processes (`ollama`, `ollama_llama_server`) now killed by name before reinstall and uninstall — prevents locked DLLs from stale Ollama instances
- `stop_backend` now also kills Ollama processes (symmetric with `start_backend` which starts both) — previously Ollama kept running after backend stop
- `/ollama/start` health endpoint now uses bundled `tools/ollama.exe` path with fallback, matching native_host.py behavior
- `pull-models-gui.py` and `/ollama/start` now set `OLLAMA_RUNNERS_DIR` env var for AppLocker compatibility

### Added

- `UsePreviousAppDir=yes` explicit directive in installer for clarity
- CUDA runner verification log at post-install — logs whether `ggml-cuda.dll` was installed correctly for GPU acceleration diagnostics
- Startup phase status indicator — shows "Starting Ollama…", "Starting backend server…", "Waiting for backend to respond…" during launch instead of a static message
- Aggressive health polling during startup (1.5s interval) for faster online transition

### Changed

- Replaced NSSM Windows services with native messaging — sidebar "Start Backend" button now starts backend and Ollama directly via OS process management
- Bundled Ollama as standalone binary in `{app}\tools\` instead of running OllamaSetup.exe — AppLocker-friendly, no external install
- Simplified installer flow — removed service registration, tray monitor, and dashboard components
- "Start Backend" now also starts Ollama automatically if not already running
- Native messaging host registered automatically at install time (no manual script required)
- Uninstaller no longer shows NSSM popup windows — clean, silent removal
- `native_host.cmd` uses venv Python instead of system PATH
- Installer scripts (`pull-models.ps1`) use bundled Ollama path instead of bare `ollama` command

### Added

- Deterministic extension ID via fixed RSA public key in manifest.json — consistent ID `inapklomefcicbehlgihcidbmboiimgc` across all machines
- Auto-generated native messaging manifest at install time with correct paths and extension ID
- Registry-based native messaging host registration (HKCU, auto-cleaned on uninstall)

### Removed

- NSSM service manager — no longer bundled or used
- System tray monitor (`tray-monitor.ps1`) — sidebar handles status display
- Dashboard GUI (`dashboard.ps1`) — sidebar replaces all dashboard functionality
- `stop-backend.ps1` — sidebar handles stop via native messaging
- `register-native-host.ps1` — installer handles registration automatically
- `launch-hidden.vbs` — was only needed for tray monitor
- `service` and `ollamasvc` installer components

## [1.13.0] — Sprint 6 Polish (2026-03-03)

### Security

- Configurable `secure` flag on session cookie via `SESSION_COOKIE_SECURE` config setting — enables secure cookies for TLS deployments
- Sanitized ticket subject in generate logs — replaced raw PII with length-only logging
- Hash-pinned Python dependencies in release workflow via `--require-hashes` for supply chain protection
- Structured audit logger (`app/services/audit.py`) for security-sensitive actions: login, logout, article delete, collection clear, shutdown — writes to rotating `audit.log` with JSON entries
- Explicit Content Security Policy in extension manifest (`script-src 'self'; object-src 'self'`)

### Changed

- Speculative third RAG query — unfiltered KB fallback now runs in parallel with filtered query via `asyncio.gather`, saving one round-trip when fallback triggers
- Narrowed MutationObserver target — tries specific ancestor elements before falling back to `document.body`
- Health polling pauses when sidebar is hidden (Visibility API) and resumes on focus
- KnowledgePanel lazy polling — doc count fetch skips when panel is collapsed
- Fixed `saveSettings` race condition — writes full state directly instead of read-merge-write
- Removed misleading settings gear icon from management SPA header

### Added

- Radix ConfirmDialog for collection Clear action (replaces inline confirmation)
- Model name tooltips in sidebar — friendly size/speed descriptions for known models
- URL import spinner indicator
- Onboarding reset button in Options page — re-shows the Getting Started guide

### Fixed

- ARIA attribute string values (PR #36) — 13 attributes across 9 components now use `"true"`/`"false"` strings

## [1.12.0] — Sprint 5 Production Hardening (2026-03-02)

### Security

- **B-SEC-1**: SQLite-backed session store (`services/session_store.py`) — sessions survive backend restarts, configurable via `SESSION_BACKEND=sqlite`; `MemorySessionStore` retained as default for dev
- **B-SEC-2**: CSRF double-submit cookie protection for Management SPA (`middleware/csrf.py`) — `whd_csrf` non-HttpOnly cookie + `X-CSRF-Token` header validation on POST/PUT/PATCH/DELETE to `/kb/`, `/ingest/`, `/feedback`; extension requests (`X-Extension-Token`) are exempt
- **B-SEC-3**: Prompt injection delimiters in LLM prompt — ticket subject, description, and custom fields wrapped in `<user_ticket_subject>`, `<user_ticket_description>`, `<user_custom_fields>` tags; additional instructions wrapped in `<user_additional_instructions>`; grounding rule added to prevent executing instructions embedded in ticket content
- **B-SEC-4**: Health endpoint scoping — `GET /health` returns minimal `{"status":"ok"}` for unauthenticated callers; detailed system info (Ollama reachability, ChromaDB counts, version) moved to `GET /health/detail` (token-gated)
- **B-SEC-5**: Localhost-only process control — `/shutdown`, `/ollama/start`, `/ollama/stop` restricted to `127.0.0.1` / `::1` connections; remote callers receive 403
- **B-SEC-6**: Path parameter validation — `article_id` constrained to `^[a-zA-Z0-9_-]{1,64}$`; feedback `doc_id` constrained to `^rated_[a-f0-9]{32}$`; invalid values return 422
- **B-SEC-7**: Replace MD5 with SHA256 for Microsoft Docs cache keys (`services/microsoft_docs.py`)

### Changed

- **Singleton services with async httpx**: LLMService, EmbedService, MicrosoftDocsService, RAGService refactored to singletons with shared `httpx.AsyncClient` connection pooling, stored on `app.state`; replaced sync `httpx.Client` + `to_thread` with native async
- **Per-key rate limiter locks**: Replaced single global `asyncio.Lock` with per-path-IP keyed locks; requests from different IPs/paths no longer serialize on a single lock
- **Parallel pinned article fetching**: Sequential pinned article loop replaced with `asyncio.gather`
- **Batch embedding in ingestion**: Parallelized chunk embedding with concurrency limit in ingestion pipeline
- Middleware stack reordered: CSRF runs innermost (after auth); `X-CSRF-Token` added to `allow_headers` in CORS config
- `extension/package.json` version synced to `1.11.0`
- `app/config.py` version synced to `1.11.0`

### Added

- **KB article index background refresh**: Stale-while-revalidate pattern — serves cached data immediately, rebuilds in background via `asyncio.create_task`; only the first cold-cache call blocks
- **Copy to clipboard**: Clipboard icon button in reply header with "Copied!" confirmation
- **Generate & Insert shortcut**: Split-button that auto-inserts reply after generation; preference stored in settings
- **Reply persistence**: Last reply per ticket URL persisted in `chrome.storage.session`; restored on navigation back
- **Configurable insert target**: Insert selector override in Options page alongside existing reader overrides; helpful error when target not found
- **Health poll backoff**: Exponential backoff when offline (5s → 15s → 30s → 60s); resets on reconnect
- **Toast notification system**: Unified toast component ported from management SPA to sidebar; replaces scattered inline messages
- `backend/app/middleware/csrf.py` — CSRF double-submit cookie middleware
- `backend/app/services/session_store.py` — abstract `SessionStore` with `MemorySessionStore` and `SQLiteSessionStore` implementations
- `backend/tests/test_csrf.py` — CSRF middleware tests
- `backend/tests/test_session_store.py` — session store tests
- `backend/tests/test_generate.py` — prompt injection delimiter tests

### Fixed

- **Accessibility**: `aria-label` on sidebar main, `aria-orientation` on tablist, improved contrast on muted text

### Test Coverage

- Backend tests: 342 (+51 new from Sprint 5)
- Extension tests: 174 (+31 new from Sprint 5)
- **Total:** 516 tests

## [1.11.0] — Sprint 4 Production Hardening (2026-03-01)

### Changed

- **L13**: Rewrite all 4 middleware classes (`SecurityHeadersMiddleware`, `APITokenMiddleware`, `RateLimitMiddleware`, `RequestSizeLimitMiddleware`) from `BaseHTTPMiddleware` to pure ASGI for streaming support and reduced memory usage
- **L17**: Replace `sessionStorage` API token in Management SPA with HttpOnly cookie session — `POST /auth/login`, `POST /auth/logout`, `GET /auth/check` endpoints, automatic session expiry and sweep

### Added

- **L10**: Backend test coverage: 23 new tests — CLI commands (`test_cli.py`), pipeline methods (`test_pipeline_extended.py`), logging config (`test_logging_config.py`)
- **L10**: Frontend test coverage: 40 new unit tests across 6 files — management API, generate reply hook, SidebarHost, content script wiring, TokenGate, useTicketData
- **L17**: Auth router (`backend/app/routers/auth.py`) with in-memory session store, 24h expiry, periodic sweep
- **L17**: `session_max_age` configuration option in backend settings
- **L27**: 15 E2E tests for Management SPA via Playwright — health, auth flow, article CRUD, article list, theme toggle
- **L27**: Playwright config with `webServer` auto-start for backend
- **L17**: 10 auth tests (`test_auth.py`) covering login/logout/check/sweep/middleware integration

### Security

- Management SPA token is now HttpOnly (JS cannot read it) + SameSite=Strict (CSRF-proof)
- Extension sidebar unchanged — still uses `X-Extension-Token` header via `chrome.storage.local`

### Test Coverage

- Extension tests: 143 (+40 new from Sprint 4)
- Backend tests: 291 (+23 new from Sprint 4)
- E2E tests: 15 (new)
- **Total:** 449 tests

## [1.10.0] — Sprint 3 (2026-03-01)

### Added

- **M10**: Documented all 18 API endpoints in `api-contract.md` (health, generation, KB CRUD, ingestion, tags/stats, feedback, settings)
- **M24**: Upload batch error recovery with per-file status tracking, partial progress, skip & continue, and retry failed
- **M26**: First-time onboarding flow with ordered setup steps card (Install Ollama → Pull model → Start backend)
- **L30**: Elapsed time counter during AI generation
- **L37**: Keyboard shortcut hint (Alt+Shift+H) in manifest

### Changed

- **L32**: Settings gear navigates to options page (was toast notification)

### Fixed

- **M6**: Rate limiter proxy limitation documented in `security.py` + `api-contract.md`
- **M7**: `/manage` static mount no-auth documented in `main.py`
- **L2**: Added CSS rule for `.import-section-label`
- **L4**: Aligned Tailwind `font-mono` with CSS tokens
- **L6**: httpx import in `pipeline.py` already top-level (stale finding, no change needed)
- **L14**: Vite 7 / Vitest 2 compatibility verified
- **L15**: Fixed installer hardcoded component index
- **L16**: Auth header skipped on `/health` endpoint requests
- **L18**: Removed Zustand stable setters from dependency arrays
- **L19**: Fixed `searchKBArticles` pagination (+4 new tests)
- **L20**: Cached DOMReader instance in content script
- **L21**: Protected `.sr-only` from tree-shaking
- **L22**: Added `aria-labelledby` to tab panels
- **L23**: Added `aria-busy` during article list refetch
- **L24**: Removed unused React imports
- **L25**: Added `SidebarHost.stop()` call on extension unload
- **L26**: Typed `handleChange` properly in OptionsPage
- **L35**: Client-side URL validation before import
- **L36**: Client-side file size check before upload
- **L39**: Warning messages stay visible after success auto-dismiss

### Test Coverage

- Extension tests: 93 (+4 new from pagination fix)
- Backend tests: 258 (unchanged)
- **Total:** 351 tests

## [1.9.0] — Sprint 2 (2026-03-01)

### Fixed

- **M1**: Async cleanup for temp files during ingestion (no blocking sleep)
- **M2**: Thread-safe article cache with `asyncio.Lock` in KB router
- **M3**: Thread-safe Microsoft Docs cache with `threading.Lock` in service
- **M4**: Article ID collision detection with distinct error messages
- **M5**: Atomic `update_article` via upsert-then-delete pattern to preserve data on failure
- **M12**: Added `uv.lock` to repository for reproducible dependency builds
- **M11**: Added auth headers (`X-Extension-Token`) to shutdown and Ollama API calls (`/ollama/start`, `/ollama/stop`)
- **M13**: Added management SPA build step to CI workflow (runs after main extension build)
- **M14**: Added `backend/static/manage/` directory to installer `setup.iss` and release workflow
- **M17**: Double-click guard on BackendControl start/stop buttons to prevent concurrent requests
- **M18**: Cleanup `setTimeout` on ArticleList unmount to prevent memory leaks
- **M19**: Pin cap toast notification + `MAX_PINNED_ARTICLES` constant extraction
- **M20**: Inline error message on feedback rating failure (replaces silent reset)
- **M21**: Success/error color differentiation for save messages in ArticleEditor
- **M22**: Model fetch failure hint in sidebar + re-fetch on reconnect
- **M23**: Network error detection in generation flow with user-facing messages
- **M25**: Undo timeout extended from 3s to 8s for accessibility
- **RI2**: `custom_fields` validation (max 10 keys, 100-char keys, 500-char values, control char stripping)
- **RI5**: Consolidated duplicate collapse triggers in BackendControl component
- **RI6**: Extracted hardcoded institution environment context to `ENVIRONMENT_CONTEXT` config setting
- **L1-L9**: Type fixes, unused `useMemo` removal, dead code cleanup (`chunk_by_paragraphs`), deduplicated utilities (`_content_id`, HTML extraction)
- **L12**: Fixed type assertion issue in management page
- **L29**: Removed unnecessary `useMemo` wrapper
- **L31**: Display property fix for feedback panel
- **L38**: Label update in ArticleEditor
- **KB Management**: Fix dark mode for confirm dialog — render Radix AlertDialog.Portal inside `.app-shell` container so CSS custom properties are inherited (H10)
- **CSS**: Dead code removal, token cleanup, transition standardization

### Changed

- API contract documentation updated to accurately reflect default values for all optional fields
- `clear_collection` error code corrected from 404 to 422 for invalid collection names

## [1.8.0] — 2026-02-28

### Added

- **KB Context Picker**: search and pin KB articles as additional context for reply generation
  - New `KBContextPicker` component in the sidebar: debounced search, pin/unpin chips
  - Pinned articles persist across generations (user clears manually)
  - Backend injects pinned article chunks as high-priority `[PINNED]` context in the AI prompt
  - `pinned_article_ids` field on the generate request (capped at 10)
  - `searchKBArticles` method added to the API client

- **Collapsible Ticket Context**: the Ticket Context section in the sidebar is now collapsible (starts expanded) with a chevron toggle, matching the pattern used by Status and Knowledge Base panels

- **Reply Ratings and Dynamic Few-Shot Examples**:
  - Reply rating buttons (thumbs up/down) in sidebar draft panel
  - `POST /feedback` endpoint stores rated replies in ChromaDB `rated_replies` collection
  - Good-rated replies used as dynamic few-shot examples in the generate prompt, replacing hardcoded examples
  - Falls back to hardcoded examples when no rated examples available (cold start)
  - Rating UI disables after one vote per generation (prevents double-rating, resets on next generation)

- **Consistency review — Backend (PR #76)**:
  - Exposed `embed_fn` public property on `EmbedService` and `upsert_stream` public method on `IngestionPipeline`
  - Replaced all hardcoded `"kb_articles"` string literals with the `KB_COLLECTION` constant

- **Consistency review — Extension UX/Hooks (PR #77)**:
  - Generate errors now surface the actual Ollama error message instead of the raw "API error 503" string
  - Replaced browser `window.confirm()` with a styled `ConfirmDialog` (Radix AlertDialog) in ArticleEditor
  - Added progress indicator to management page file upload (previously showed bare "Uploading..." text)
  - ManageTab collection clear now shows success/error feedback after the operation
  - Management import errors now surface the actual backend error detail to the user
  - Added `aria-label`, `aria-controls`, and `role="tabpanel"` to KnowledgePanel tab strip
  - Extracted `DEFAULT_TAG_SUGGESTIONS` to a shared constants file (was duplicated across two components)

- **Consistency review — Extension UI/CSS (PR #75)**:
  - Added `.ok-text` / `.warn-text` modifier classes to sidebar CSS
  - Added semantic `.icon-btn` class; settings gear button no longer misuses `.theme-toggle`

- **KB Article Editing**: edit title, content, and tags of manually created articles after saving
  - `PUT /kb/articles/{article_id}` endpoint: re-chunks and re-embeds content while preserving original article ID and import timestamp
  - Only `source_type: "manual"` articles can be edited (returns 403 for imported articles)
  - Edit mode in KB Management page: "Edit Article" button in article detail view (manual articles only)
  - `ArticleEditor` component supports both create and edit modes with content reconstruction from chunks
  - Request size middleware updated to support sub-path exemptions for large article payloads
  - CORS methods expanded to include PUT and PATCH
  - 11 new backend tests, 4 new frontend tests

### Changed

- **Consistency review — Extension UI (PR #78)**:
  - Theme toggle icon moved to the right of the Status heading in the sidebar

- **Consistency review — Extension UI/CSS (PR #75)**:
  - Aligned Tailwind config accent colour to match actual CSS value (`#0969da`)
  - Removed Tailwind utility classes from `SkeletonLoader`, `InsertButton`, and `ErrorBoundary` — these components are now CSS-class-only
  - Unified primary button font-weight and skeleton animation across sidebar and management page
  - Multiple CSS token and link-button consistency fixes between sidebar and management surfaces

- **Consistency review — Backend (PR #76)**:
  - Unified error response mechanism — all routers now use `HTTPException` (previously mixed with raw `JSONResponse`)
  - Standardised time measurement to `perf_counter()` across all routers
  - Renamed `chunks_created` → `chunks_ingested` in `UpdateArticleResponse`
  - Updated backend version string to `1.7.0`

### Fixed

- **Consistency review — Backend (PR #76)**:
  - Fixed double-nested `detail` field in 503 error responses from the generate and models endpoints
  - Added unconditional auth guard to `/shutdown`, `/ollama/start`, and `/ollama/stop` endpoints (guard was previously bypassable)
  - Fixed `clear_collection` returning 404 instead of 422 for unknown collection names
  - Consolidated KB response models into a single file; deleted dead `SourceTypeCount` class

- **Consistency review — Extension UI/CSS (PR #75)**:
  - Fixed invisible active pagination button caused by missing `--accent-subtle` CSS variable

- **Consistency review — Extension UX/Hooks (PR #77)**:
  - Fixed `TokenGate` showing a blank gate screen on invalid token — now shows an "Invalid token" error message

## [1.7.0] - 2026-02-28

### Changed

- **UI overhaul — "Precision Utility" design system**: complete visual refresh across all 3 web surfaces (sidebar, options page, KB management page), replacing generic aesthetics with a GitHub Primer-inspired palette and developer-tool aesthetic
  - **Sidebar**: removed redundant app header (Edge panel title suffices), theme toggle relocated into Status panel, gradient brand mark replaced with clean text, status chips now use dot + text instead of colored pill backgrounds, tighter 4px-grid spacing, 120ms transitions throughout
  - **Options page**: restructured into 4 named sections (Connection, Model & Prompt, Appearance, Advanced), uppercase section labels, custom select chevrons, collapsible DOM selectors with left accent border
  - **KB management page**: stat cards replaced with compact horizontal stat bar, article rows thinned and cleaned up, muted source badges, subtle skeleton pulse (not shimmer), Import button demoted to secondary style, active page number uses subtle highlight instead of solid blue block
  - **Shared**: new color tokens (light: #f6f8fa bg, #0969da accent; dark: #0d1117 bg, #4493f8 accent), `Segoe UI Variable` font stack, monospace for data values, consistent 6px border-radius, no heavy shadows

### Fixed

- **Tag autocomplete**: inline tag editing in ArticleDetail now shows datalist autocomplete with all 27 WHD request types and existing tags from the database
- **Missing request types**: added 10 missing WHD request types to DEFAULT_TAG_SUGGESTIONS
- **ArticleEditor autocomplete**: tag input in article creation now also shows inline datalist suggestions while typing
- **CHANGELOG formatting**: replaced inline styles with CSS classes in CHANGELOG rendering

### Added

- **KB Article Tagging**: tag articles with WHD request types (e.g., NETWORK CONNECTION, MAILBOX) for category-filtered RAG retrieval
  - `PATCH /kb/articles/{id}/tags` endpoint: update tags on all chunks of an article
  - `GET /kb/tags` endpoint: returns all unique tags across articles (for autocomplete)
  - `CreateArticleRequest` accepts optional `tags` array, stored as comma-separated string in ChromaDB chunk metadata
  - Tag validation: rejects commas (storage delimiter), strips whitespace, max 20 tags / 100 chars each
  - Two-phase RAG retrieval: when ticket category is set, phase 1 queries KB with `$contains` tag filter, phase 2 backfills remaining slots unfiltered with deduplication
  - `category` parameter passed from `/generate` to RAG service in both web-context code paths
  - Article index cache merges tags across chunks (set union)
  - Tag picker UI in ArticleEditor: pill display, Enter/comma to add, paste support, datalist autocomplete from existing tags
  - Inline tag editing in ArticleDetail: view/edit mode toggle with Save/Cancel and error toast
  - 12 new backend tests (tag CRUD, validation, filtered RAG), 2 new frontend tests
- **Auto-Generate API Token**: installer generates a secure API token during setup and the extension auto-detects it — zero manual configuration
  - `post-install.ps1` generates 32-byte hex token and writes to `backend/.env` from `.env.example` template
  - `get_token` native messaging action reads token from `.env` for the extension
  - `chrome.runtime.onInstalled` auto-provisions token on first install via native messaging
  - "Auto-detect" button in Options page for manual token re-sync
  - Upgrade-safe: existing `.env` is never overwritten
- **Article Editor UX improvements**: content template, tag picker, and cross-navigation
  - Pre-filled Markdown template (Problem / Solution / Additional Notes) for new articles
  - Collapsible "Browse request types" picker with all 17 WHD request types as clickable chips
  - Cross-links: Options page links to KB Management, KB Management gear icon shows extension settings hint
  - `options-btn-secondary` CSS class for secondary action buttons
- **Create Article from Scratch**: full-page Markdown editor in KB Management page for authoring knowledge articles directly
  - `POST /kb/articles` endpoint: generates article ID, chunks by `##`/`###` headings, embeds via Ollama, stores in ChromaDB as `source_type: "manual"`
  - `chunk_by_markdown_headings()` utility: splits Markdown by headings, auto-creates "Introduction" section for pre-heading content, sub-splits oversized sections
  - `ArticleEditor` React component: title input + monospace textarea, Ctrl+S/Cmd+S save, unsaved-changes warning, inline error display for duplicates (409)
  - "New Article" button with pencil icon in KB Management header
  - "Manual" option in source type filter, teal badge for manual articles
  - Shared ingestion semaphore extracted to `shared.py` (prevents concurrent ingestion across file upload, URL, and article creation)
  - Request size exemption for `/kb/articles` (articles can exceed 64KB default limit)
  - 20 new backend tests (chunker + endpoint), 7 new frontend tests

## [1.6.0] - 2026-02-27

### Added

- **KB Management Page**: standalone web UI at `localhost:8765/manage` for browsing, searching, importing, and deleting knowledge base articles
  - 4 new backend endpoints: `GET /kb/articles` (paginated, filterable), `GET /kb/articles/{id}` (detail with chunks), `DELETE /kb/articles/{id}`, `GET /kb/stats`
  - Server-side article index cache (5 min TTL) for fast list/stats queries, invalidated on mutations
  - React SPA with 14 components: Header, StatCards, ArticleList, ArticleRow, ArticleDetail, ImportSection, SearchBar, SourceFilter, Pagination, ConfirmDialog, Toast, EmptyState, TokenGate, SkeletonTable
  - React Query (`@tanstack/react-query`) for server state management with optimistic deletes
  - Radix AlertDialog for accessible delete confirmations
  - Full dark/light theme support using shared CSS design tokens
  - sessionStorage-based auth reusing existing `X-Extension-Token` mechanism (zero backend auth changes)
  - Served as static SPA via FastAPI `StaticFiles` at `/manage`
- `imported_at` ISO 8601 timestamp added to chunk metadata for HTML, PDF, and URL ingestion
- `DELETE` added to CORS `allow_methods`
- 22 new backend tests for KB management endpoints

## [1.5.0] - 2026-02-27

### Added

- **Microsoft Learn Live Search**: at generation time, searches Microsoft Learn for relevant documentation and includes results as additional RAG context (#57)
  - Runs in parallel with local ChromaDB retrieval via `asyncio.gather()` — no added latency
  - `MicrosoftDocsService` with in-memory cache (5 min TTL, 128 max entries)
  - Domain-locked fetching: only `learn.microsoft.com` articles are fetched
  - Privacy-conscious: only ticket subject + category used as search keywords
  - Configurable via `microsoft_docs_enabled` config and `include_web_context` request field
  - Graceful degradation: search failures return empty list, generation continues with local context only
- **URL Ingestion**: `POST /ingest/url` endpoint to fetch a URL, extract content, and store in ChromaDB (#56)
  - BeautifulSoup extraction: strips script, style, nav, footer, header, aside elements
  - Chunks with existing `chunk_by_tokens()` (500 tokens, 50 overlap)
  - Shares concurrency semaphore with file upload (one ingestion at a time)
  - Sidebar URL input in Import tab with loading/success/error states
  - `apiClient.ingestUrl()` method in extension
- CI concurrency group on Claude Code Review workflow to prevent duplicate runs (#58)
- `web_docs` count in generate log line for observability (#59)
- 56 new tests: 11 MS Learn service, 33 URL loader (including SSRF vectors), 8 ingest endpoint, 4 extension API client

### Security

- **SSRF prevention for URL ingestion**: private IP blocking (IPv4/IPv6/IPv4-mapped), DNS resolution before connection, redirect re-validation per hop, scheme whitelist (http/https), 5 MB response cap, Content-Type whitelist (#56)
- Domain validation for Microsoft Learn article fetching — only `learn.microsoft.com` URLs are fetched (#57)

## [1.4.0] - 2026-02-27

### Added

- **Knowledge Import GUI**: sidebar panel with Import/Manage tabs for uploading documents (PDF, HTML, JSON, CSV) directly into ChromaDB (#51)
  - Drag-and-drop file upload with progress tracking and cancel support
  - Collection management: view document counts, clear collections with inline confirmation
  - `useKnowledgeImport` hook with file staging, sequential upload, abort, auto-dismiss
  - `KnowledgePanel`, `ImportTab`, `ManageTab` components following Fluent Design system
- Backend `POST /ingest/upload` endpoint with multipart file upload, streaming size check, and concurrency semaphore (#51)
- Backend `POST /ingest/collections/{name}/clear` endpoint for idempotent collection reset (#51)
- `IngestionPipeline.ingest_file()` method with auto-routing by file extension (#51)
- `embed_fn` injection into `IngestionPipeline` for reusable embedding logic (#51)
- Batch logging in `_upsert_stream` for ingestion progress visibility (#51)
- PDF 500-page cap in `load_kb_pdf` to prevent memory issues (#51)
- `max_upload_bytes` config setting (default 50 MB) (#51)
- Middleware `exempt_paths` for upload endpoint size limit bypass (#51)
- Per-path rate limiting: `/ingest/upload` at 5 req/min (#51)
- 27 new backend tests: upload endpoint, collection clear, pipeline routing, middleware exemption (#51)
- 18 new extension tests: API client ingest methods, hook logic, component rendering (#51)
- Claude Code Review as required CI check with write permissions (#52)

## [1.3.0] - 2026-02-27

### Added

- Unit tests for LLMService and EmbedService (19 tests) (#47)
- Security middleware tests for rate limiting and request size (17 tests) (#49)
- CORS wildcard validation — rejects `CORS_ORIGIN=*` when `API_TOKEN` is set (#45)
- Config validation tests for CORS + token combinations (#45)

### Fixed

- Unhandled exceptions in RAG retrieve path now return 503 instead of 500 (#44)
- JSON parse error handling in LLM service, embed service, and models router (#44)
- querySelector crash from invalid user-supplied selectors in content script (#46)
- Missing `resp.ok` checks in api-client `health()`, `ollamaStart()`, `ollamaStop()` (#46)
- Memory leak in RateLimitMiddleware — stale IP entries now evicted (#43)
- Redundant type assertions removed in service-worker.ts (#46)

### Security

- Pinned Ollama, uv, and NSSM versions in release workflow with SHA256 checksums (#48)
- Supply chain hardening: all downloaded binaries verified before use (#48)

## [1.2.0] - 2026-02-24

### Added

- Cancel generation button with AbortController support (#40)
- Editable reply draft with Edit/Preview toggle before insertion (#40)
- Dark mode support on Options page with CSS custom properties (#41)
- Structured JSON logging for backend with `JSONFormatter` (#42)
- Retry logic (2 retries, 1s delay) for LLM and embedding services (#42)
- `prompt_suffix` field wired end-to-end (extension settings to backend prompt) (#42)
- Installer service dashboard GUI with live health polling (#23)
- Uninstall cleanup dialog for Ollama runtime and model data (#23)
- Logging for auth failures and rate limit events in middleware (#42)

### Changed

- ErrorBoundary now renders inside themed `.app-shell` div for dark mode coverage (#41)
- Options page uses theme-aware CSS classes instead of hardcoded Tailwind colors (#41)
- Backend `httpx` calls handle `TimeoutException` in addition to `ConnectError` (#42)

### Fixed

- Timing-safe token comparison using `secrets.compare_digest()` (#39)
- `/shutdown`, `/ollama/start`, `/ollama/stop` now require API token authentication (#39)
- DOMReader race condition resolved with `_ready` Promise gate (#39)
- Negative cosine similarity scores clamped to zero in RAG service (#39)
- Content ID hashing uses full document content instead of first 200 chars (#39)
- `console.log`/`console.error` replaced with gated `debugLog`/`debugError` utilities (#39)
- Deprecated `asyncio.get_event_loop()` replaced with `asyncio.create_task()` (#39)

### Removed

- LangChain dependencies (~500 MB reduction in backend install size) (#42)

### Dependencies

- Bump `fastapi` from 0.131.0 to 0.132.0 (#32)
- Bump `actions/checkout` to v6 (#26)
- Bump `actions/upload-artifact` to v6 (#27)
- Bump `actions/download-artifact` to v7 (#25)
- Bump `Minionguyjpro/Inno-Setup-Action` to 1.2.7 (#28)

## [1.1.0] - 2026-02-24

### Added

- Sidebar service control panel (start/stop backend and Ollama from extension)
- Dark mode with system preference detection and manual toggle
- Label-based DOM extraction fallback for WHD table layout
- System tray monitor for backend health status
- Fully offline installer release package
- Native messaging host for backend process management

### Fixed

- Single-instance mutex on tray monitor to prevent duplicates
- UX polish: real icons, hidden Ollama service window, build verification (#20)

### Changed

- Version bump to 1.1.0 across all packages

## [1.0.1] - 2026-02-19

### Fixed

- Ollama detection, Edge path resolution, and install directory in installer (#18)
- Removed CLAUDE.md from published repo (#17)
- Gitignored `uv.lock` for cleaner diffs (#17)

## [1.0.0] - 2026-02-19

### Added

- FastAPI backend with `/generate`, `/health`, `/models` endpoints
- RAG pipeline with ChromaDB vector store and `nomic-embed-text` embeddings
- Ollama integration for local LLM inference (`llama3.2:3b`)
- Edge extension (Manifest V3) with sidebar panel
- Content script with DOM reader for WHD ticket fields
- Native textarea inserter using setter trick
- Options page with selector overrides editor
- API token authentication middleware
- Rate limiting and request size limiting middleware
- Security headers middleware
- Keyboard navigation and ARIA accessibility labels
- Inno Setup Windows installer with NSSM service management
- CI/CD pipeline with GitHub Actions
- Backend middleware and models router tests
- Extension sidebar store, DOM inserter, and storage tests

[1.6.0]: https://github.com/gyzhoe/assistant/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/gyzhoe/assistant/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/gyzhoe/assistant/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/gyzhoe/assistant/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/gyzhoe/assistant/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/gyzhoe/assistant/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/gyzhoe/assistant/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/gyzhoe/assistant/releases/tag/v1.0.0
