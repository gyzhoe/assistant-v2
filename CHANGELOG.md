# Changelog

All notable changes to AI Helpdesk Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.2.0]: https://github.com/gyzhoe/assistant/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/gyzhoe/assistant/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/gyzhoe/assistant/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/gyzhoe/assistant/releases/tag/v1.0.0
