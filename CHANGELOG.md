# Changelog

All notable changes to AI Helpdesk Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.5.0]: https://github.com/gyzhoe/assistant/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/gyzhoe/assistant/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/gyzhoe/assistant/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/gyzhoe/assistant/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/gyzhoe/assistant/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/gyzhoe/assistant/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/gyzhoe/assistant/releases/tag/v1.0.0
