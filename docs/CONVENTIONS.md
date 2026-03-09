# Codebase Conventions

Single source of truth for all coding patterns. Agents MUST follow these in every PR.

---

## 1. Versioning

### Semantic Versioning
- **Format**: `MAJOR.MINOR.PATCH` per [semver.org](https://semver.org/spec/v2.0.0.html)
- **MAJOR**: Breaking changes (API contracts, extension manifest format, DB schema migrations)
- **MINOR**: New features, new endpoints, new UI components
- **PATCH**: Bug fixes, polish, refactors that don't change behavior

### Where Versions Live (keep in sync)
| File | Field | Example |
|---|---|---|
| `backend/pyproject.toml` | `version = "X.Y.Z"` | `version = "2.0.0"` |
| `extension/public/manifest.json` | `"version": "X.Y.Z"` | `"version": "2.0.0"` |

### When to Bump
- **Every release** bumps both files + adds a dated `## [X.Y.Z]` header in CHANGELOG.md
- **Between releases**: work goes under `## [Unreleased]` — no version bump until release
- **Hotfixes**: bump PATCH immediately (`2.0.0` → `2.0.1`)
- **Feature sprints**: bump MINOR at sprint end (`2.0.0` → `2.1.0`)
- **Breaking changes**: bump MAJOR (rare — coordinate with team)

### CHANGELOG Format
```markdown
## [Unreleased] — Short Sprint Name

### Added
- **Feature name** — description of what was added

### Changed
- **Feature name** — description of what changed

### Fixed
- **Bug name** — description of what was fixed

### Removed
- **Feature name** — description of what was removed
```
- Follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
- Use **bold** for the feature/fix name, em dash, then description
- Group by track/domain for multi-track sprints (e.g., `#### Track A — Backend`)

---

## 2. Error Responses (Backend)

### Standard Envelope
ALL API errors MUST use `ErrorResponse`:
```python
class ErrorResponse(BaseModel):
    message: str        # Human-readable, actionable
    error_code: ErrorCode  # Machine-readable UPPER_SNAKE_CASE
```

### Error Codes (`ErrorCode` StrEnum in `response_models.py`)
Current codes (13): `LLM_DOWN`, `MODEL_ERROR`, `INTERNAL_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `RATE_LIMITED`, `PAYLOAD_TOO_LARGE`, `EMBED_DOWN`, `INGESTION_BUSY`, `SERVICE_UNAVAILABLE`.
Expand as needed — always UPPER_SNAKE_CASE, descriptive.

### Raising Errors in Routers
Use `HTTPException` — the global handler in `main.py:205` normalizes ALL to `{message, error_code}`:
```python
raise HTTPException(status_code=422, detail="No filename provided")
# Global handler auto-maps to ErrorResponse with appropriate error_code
```
For explicit control, pass a dict as detail:
```python
raise HTTPException(status_code=409, detail={"message": "Ingestion busy", "error_code": "INGESTION_BUSY"})
```
Or use the `error_response()` helper from `response_models.py` to return directly.

### Middleware Errors
Use `send_json_error()` ASGI helper with both `message` and `error_code`:
```python
await send_json_error(send, 401, {"message": "Unauthorized.", "error_code": "UNAUTHORIZED"})
```

### Error Message Tone
- **Be specific**: "Unsupported file type: .docx. Allowed: .json, .csv, .html, .htm, .pdf"
- **Be actionable**: tell the user what went wrong AND what to do
- **No jargon**: "Could not reach LLM server" not "ECONNREFUSED on socket"
- **Include context**: mention the resource that failed (filename, URL, model name)

---

## 3. Backend Test Conventions

### Framework & Setup
- **pytest** + **pytest-asyncio** with `anyio_backend = "asyncio"`
- Async tests: `@pytest.mark.asyncio` decorator
- HTTP testing: `httpx.AsyncClient` with `ASGITransport` (no real HTTP)
- Fresh app per test when isolation matters: `create_app()` from test helpers

### Fixtures
- Shared fixtures in `conftest.py` — keep minimal, prefer per-test setup
- `setup_app_state(app)` helper injects mock services into `app.state`
- Use `@pytest_asyncio.fixture` for async fixtures

### Mocking
- **Preferred**: `unittest.mock.MagicMock` + `AsyncMock`
- **Pattern**: inject mocks via `app.state.service = mock_instance`
- **No monkeypatch for services** — use app state injection
- Helper functions for complex mocks: `_mock_ms_docs()`, `_mock_rag_service()`

### Test Naming
```
test_<action>_<expected_outcome>
```
Examples:
- `test_health_returns_200`
- `test_generate_without_subject_returns_200`
- `test_login_invalid_token_returns_401`
- `test_upload_unsupported_filetype_returns_422`

### Assertions
```python
assert response.status_code == 200
data = response.json()
assert data["reply"] != ""
assert data["error_code"] == "LLM_DOWN"
```
Use `pytest.raises()` for expected exceptions in unit tests.

### Test File Naming
```
tests/test_<module>.py
```
Example: `test_health.py`, `test_generate.py`, `test_auth.py`

---

## 4. Frontend Test Conventions

### Framework & Setup
- **Vitest** with `describe` / `it` / `expect`
- File naming: `*.test.ts` or `*.test.tsx` (never `.spec`)
- Setup/teardown: `beforeEach(() => { vi.clearAllMocks(); })`

### Mocking
- **Globals**: `vi.stubGlobal('chrome', { ... })`, `vi.stubGlobal('fetch', mockFetch)`
- **Functions**: `vi.fn()` for spies, `.mockResolvedValueOnce()` for async returns
- **Chrome API**: stub entire `chrome` object at file level
- **Fetch**: `mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({...}) })`
- **Gotcha**: `vi.restoreAllMocks()` undoes `vi.stubGlobal` — re-apply in `beforeEach`

### Zustand Store Tests
- Reset store state in `beforeEach`: `store.setState({ ... })`
- Test state transitions, not implementation details

### Test Naming
```typescript
it('sets generation status when generate starts')
it('calls /api/generate with correct body')
it('handles network error gracefully')
```
Descriptive sentences, not function signatures.

### Component Tests
- Use `@testing-library/react`: `render()`, `screen.getByRole()`, `userEvent`
- **jsdom stubs needed**:
  - `Element.prototype.scrollIntoView = vi.fn()`
  - `vi.stubGlobal('matchMedia', ...)`

### Test File Location
```
extension/tests/unit/<name>.test.ts
```

---

## 5. API Response Schemas

### All Responses Are Pydantic Models
Every endpoint returns a typed Pydantic `BaseModel`. No raw dicts.

### Success Response Patterns
```python
# Single resource
class GenerateResponse(BaseModel):
    reply: str
    model_used: str
    context_docs: list[ContextDoc]
    latency_ms: int

# List response (with pagination when applicable)
class ArticleListResponse(BaseModel):
    articles: list[ArticleSummary]
    total_chunks: int
    total_pages: int  # ceiling division of total / page_size

# Mutation response
class CreateArticleResponse(BaseModel):
    article_id: str

# Simple list
class TagListResponse(BaseModel):
    tags: list[str]
```

### Optional Fields
Use `field: Type | None = None` (not `Optional[Type]`):
```python
warning: str | None = None
title: str | None = None
```

### Naming
- `<Action><Resource>Response` — e.g., `CreateArticleResponse`, `IngestUploadResponse`
- List responses: `<Resource>ListResponse`
- Error: always `ErrorResponse`

---

## 6. Service Layer

### Structure
- **Class-based**, one class per domain: `LLMService`, `EmbedService`, `RAGService`
- **Singleton** — instantiated once in `lifespan()`, stored on `app.state`
- **No FastAPI `Depends()`** for services — access via `request.app.state.<service>`

### Dependency Injection
```python
# In lifespan():
app.state.llm_service = LLMService(client=http_client)

# In router:
llm = request.app.state.llm_service
```

### Error Handling
- Services **raise exceptions** (not return Result types)
- Custom exceptions: `LLMModelError`, `ConnectionError`
- Global exception handlers in `main.py` catch and wrap in `ErrorResponse`
- Routers should NOT try/except service errors (let them bubble to handlers)

### Private vs Public Attributes
- Internal state: `self._client`, `self._cache`
- Public access: add `@property` getter (e.g., `embed_service.client`)
- Never access `service._private` from outside the class

---

## 7. Logging

### Setup
- Standard library `logging` module with custom `JSONFormatter`
- Structured JSON output: `{timestamp, level, logger, message, exception}`
- `setup_logging(level="INFO")` called in `main.py`

### Log Levels
| Level | When to Use | Example |
|---|---|---|
| `DEBUG` | Detailed diagnostic info | "Could not probe /v1/models, using default" |
| `INFO` | Startup events, successful operations | "Detected loaded model: qwen3.5:9b" |
| `WARNING` | Transient failures, retries | "LLM generate attempt 2 failed, retrying..." |
| `ERROR` | Unrecoverable errors | "Failed to connect to ChromaDB" |

### Audit Logging
- Security-sensitive actions use `audit_log()` from `app/services/audit.py`
- Always include: action, client_ip, outcome
- Actions: login, logout, shutdown, delete operations

### Rules
- Never log secrets, tokens, or PII
- Use `%s` formatting (not f-strings) for lazy evaluation: `logger.info("Model: %s", model)`
- One logger per module: `logger = logging.getLogger(__name__)`

---

## 8. Constants & Configuration

### Backend Constants (`app/constants.py`)
- All magic numbers live here — never inline
- Naming: `UPPER_SNAKE_CASE`
- Examples: `DEFAULT_CHUNK_MAX_TOKENS = 500`, `LLM_MAX_RETRIES = 2`

### Backend Config (`app/config.py`)
- `pydantic-settings` `BaseSettings` class
- Reads from `.env` file
- Access via `settings = get_settings()` (cached)
- All config has type hints and defaults

### Request Validation (`app/models/request_models.py`)
- Max lengths as module-level constants: `_SUBJECT_MAX = 500`, `_DESCRIPTION_MAX = 16_000`
- Enforced via Pydantic `Field(max_length=...)`
- Naming: `_UPPER_SNAKE` (private to module)

### Frontend Constants (`src/shared/constants.ts`)
- `DEFAULT_BACKEND_URL`, `STORAGE_KEY_SETTINGS`, `NATIVE_HOST`
- `OBSERVER_DEBOUNCE_MS`, `DEFAULT_SELECTORS`
- Export individually (not a namespace object)

---

## 9. CSS & Design Tokens

### Token System
All colors via CSS custom properties — **never hardcode hex values**.

```css
/* Light theme (default) */
--accent: #0078d4;       /* Primary blue */
--bg: #f6f8fa;           /* Page background */
--surface: #ffffff;      /* Card/panel background */
--text: #1f2328;         /* Primary text */
--muted: #656d76;        /* Secondary text */
--border: #d0d7de;       /* Borders */
--error: #d1242f;        /* Error states */
--ok: #1a7f37;           /* Success states */
--warn: #9a6700;         /* Warning states */

/* Dark theme via [data-theme='dark'] */
```

### Rules
- Use `var(--token)` everywhere — no raw `#hex` or `rgb()` in component CSS
- Both themes must work — test light AND dark
- New tokens only when semantically distinct from existing ones
- Transitions: 120ms standard (defined in `sidebar.css`)
- Sidebar viewport is ~360px — test at narrow width

---

## 10. Git & Code Quality

### Commits
- **Conventional Commits**: `feat(scope):`, `fix(scope):`, `chore:`, `docs:`, `test:`, `perf:`
- Scopes: `backend`, `extension`, `installer`
- Message: imperative mood, lowercase, no period

### Branches
- `feat/`, `fix/`, `chore/`, `docs/`, `test/`, `perf/` prefixes off `main`

### Type Safety
- **Python**: type hints on all functions, `mypy --strict`, no `# type: ignore` without comment
- **TypeScript**: `strict: true`, no `any`, no `// @ts-ignore`, no `console.log` (use `debugLog`)

### Code Cleanliness
- No dead code, no commented-out code, no TODOs
- No `print()` in backend (use `logger`)
- No `console.log` in extension (use `debugLog`/`debugError`)
