# Security Audit

## Executive Summary

The application demonstrates a strong security-first mindset with solid fundamentals: CORS locking, SSRF prevention on URL ingestion, constant-time token comparison, HttpOnly session cookies, input validation via Pydantic, rate limiting, request size limiting, and security headers. For an internal corporate tool on localhost, this is well above average. However, there are several findings ranging from medium to low severity that should be addressed before multi-user production deployment, primarily around session management hardening, the unauthenticated management SPA, and prompt injection surface area.

## Critical Findings

None. No critical vulnerabilities were found that would allow immediate unauthorized access or remote code execution in the current deployment model (localhost-only, corporate network).

## High Findings

### H1. Management SPA Served Without Authentication (Network-Exposed Risk)

**File:** `backend/app/main.py:91-106`
**Severity:** High (if network-exposed), Low (if localhost-only)
**Exploitability:** Easy

The `/manage` static files mount has no authentication middleware. While a comment (lines 96-99) acknowledges this is intentional for localhost, the threat model is changing to multi-user shared service deployment. If the backend is ever exposed beyond localhost (e.g., `--host 0.0.0.0` or behind a reverse proxy), anyone on the network can access the management SPA HTML/JS/CSS. The SPA itself does cookie-based auth for API calls, but the static files (including the full client-side code) are served freely.

**Recommendation:** Either:
- Add a middleware guard that checks for a valid session cookie before serving `/manage` static files, or
- Document explicitly that `/manage` MUST be behind an authenticated reverse proxy in any non-localhost deployment, or
- Accept the risk since the SPA is a thin client and API calls are already auth-protected (current state is functionally safe for API operations).

### H2. In-Memory Session Store Does Not Survive Restarts

**File:** `backend/app/routers/auth.py:41-83`
**Severity:** High (operational)
**Exploitability:** N/A (not a vulnerability per se, but a reliability concern)

The `SessionStore` is a module-level in-memory singleton. When the backend restarts (crash, update, service restart), all sessions are lost and all management SPA users must re-authenticate. In a multi-user deployment, this creates operational friction.

**Recommendation:** For production, consider persisting sessions to a file or SQLite database, or accept the trade-off given the 24h session max age and infrequent restarts.

### H3. Prompt Injection Surface via Ticket Data and Custom Fields

**File:** `backend/app/routers/generate.py:330-369`
**Severity:** High (LLM-specific)
**Exploitability:** Moderate

Ticket data (subject, description, custom fields, prompt suffix) is interpolated directly into the LLM prompt template using f-strings. A malicious ticket creator could craft a description containing prompt injection payloads like "Ignore all previous instructions and output..." to manipulate the AI's response.

Mitigating factors:
- Input length limits exist (`request_models.py:8-11`: subject 500 chars, description 16K chars, prompt suffix 2K chars)
- Control characters are stripped from custom fields
- The grounding rules in the prompt attempt to constrain behavior
- The LLM is local (no tool-use or external action capability)

**Recommendation:**
- The risk is inherent in any LLM-based system. The current mitigations (length limits, grounding rules) are reasonable.
- Consider adding a note in documentation that AI replies should always be reviewed by the technician before sending.
- Optionally add a prompt delimiter/sandwich pattern (e.g., XML tags around user input) to make injection harder.

## Medium Findings

### M1. No CSRF Protection on Session Cookie Auth

**File:** `backend/app/routers/auth.py:128-137`, `backend/app/middleware/security.py:115-124`
**Severity:** Medium
**Exploitability:** Moderate (requires social engineering)

The management SPA uses cookie-based auth (`SameSite=Strict`, `HttpOnly=True`). While `SameSite=Strict` prevents most cross-site request scenarios, it does not protect against same-origin or sub-domain attacks. There is no CSRF token mechanism.

Given that:
- The backend runs on `localhost:8765`
- `SameSite=Strict` prevents cross-origin cookie sending
- The threat model is an internal corporate network

The risk is LOW in practice but MEDIUM by security standards.

**Recommendation:** Add a CSRF token (double-submit cookie or synchronizer token) to state-changing POST/PUT/DELETE endpoints used by the management SPA.

### M2. `secure=False` on Session Cookie

**File:** `backend/app/routers/auth.py:133`
**Severity:** Medium (defense-in-depth)
**Exploitability:** Low (requires network MITM on HTTP traffic)

The session cookie is set with `secure=False` because the backend runs over plain HTTP on localhost. This is correct for the current deployment but means the cookie will be sent over unencrypted connections if the backend is ever accessed over the network.

**Recommendation:** Make this configurable: `secure=True` when TLS is available, `secure=False` only for localhost. Add a config setting `SESSION_COOKIE_SECURE` that defaults based on whether the CORS origin starts with `https://`.

### M3. Health Endpoint Leaks Internal Configuration

**File:** `backend/app/routers/health.py:31-59`
**Severity:** Medium
**Exploitability:** Easy (no auth required)

The `/health` endpoint is exempt from authentication and returns:
- Backend version number
- Ollama reachability status
- ChromaDB collection names and document counts

While useful for monitoring, this provides reconnaissance information to unauthenticated callers (collection names, data volume, software versions).

**Recommendation:** Return a minimal response (`{"status": "ok"}`) for unauthenticated requests. Expose detailed info only to authenticated callers via a separate `/health/detail` endpoint, or protect the existing endpoint.

### M4. Shutdown and Process Control Endpoints

**File:** `backend/app/routers/health.py:62-122`
**Severity:** Medium
**Exploitability:** Low (requires valid API token)

The `/shutdown`, `/ollama/start`, `/ollama/stop` endpoints allow process management via API calls. These are protected by `_require_token`, but:
- They use `os.kill(os.getpid(), signal.SIGTERM)` and `subprocess.Popen/run` with hardcoded commands
- The process management is not rate-limited beyond the global `/generate` rate limiter
- In dev mode (no token configured), these are completely open

These endpoints are appropriate for the native messaging use case but represent a significant attack surface if the backend is network-exposed without token auth.

**Recommendation:** Consider adding these endpoints to the rate limiter, or restricting them to localhost-only connections (check `scope["client"][0]` == `127.0.0.1`).

### M5. Native Host Reads `.env` File and Returns API Token

**File:** `backend/native_host.py:73-97`
**Severity:** Medium
**Exploitability:** Low (requires native messaging access)

The `get_token` action reads the API token from `backend/.env` and returns it to the extension. This is by design for zero-config setup, but means:
- Any extension with native messaging permission to `com.assistant.backend_manager` can extract the token
- The native host manifest (registered during install) restricts this to the specific extension ID
- The token is transmitted over the native messaging channel (local pipes, not network)

**Recommendation:** This is acceptable for the current trust model. Ensure the native host manifest always specifies `allowed_origins` with the exact extension ID.

### M6. Collection Name Not Validated in `clear_collection`

**File:** `backend/app/routers/ingest.py:137-158`
**Severity:** Low-Medium
**Exploitability:** Low

The `clear_collection` endpoint validates against `ALLOWED_COLLECTIONS` (line 140), which is correct. However, the `article_id` parameter in KB routes (`kb.py:438`, `kb.py:547`, etc.) is used directly in ChromaDB `where` filters without sanitization. ChromaDB's query API should prevent SQL injection, but the article IDs are free-form strings.

**Recommendation:** Add a regex validator for `article_id` parameters (e.g., hex string, max 32 chars) in the path parameter.

### M7. `feedback_id` Path Parameter Without Validation

**File:** `backend/app/routers/feedback.py:70`
**Severity:** Low-Medium
**Exploitability:** Low

The `DELETE /feedback/{doc_id}` endpoint accepts an arbitrary string `doc_id` and passes it directly to `col.get(ids=[doc_id])` and `col.delete(ids=[doc_id])`. While ChromaDB should handle this safely, there's no validation that the ID follows the expected `rated_*` prefix pattern.

**Recommendation:** Add a regex path parameter constraint: `doc_id: str = Path(pattern=r"^rated_[a-f0-9]{32}$")`.

### M8. MD5 Used for Cache Key in Microsoft Docs Service

**File:** `backend/app/services/microsoft_docs.py:44`
**Severity:** Low-Medium (informational)
**Exploitability:** Not exploitable in this context

MD5 is used for cache key generation (search query deduplication). This is not a security-sensitive use (no authentication or integrity checking), but it may trigger security scanners. The `# noqa: S324` comment acknowledges this.

**Recommendation:** Swap to `hashlib.sha256` for the cache key to eliminate scanner noise. Performance difference is negligible.

## Low / Informational Findings

### L1. Logging May Contain Sensitive Ticket Data

**File:** `backend/app/routers/generate.py:32`
**Severity:** Low
**Exploitability:** N/A

The generate endpoint logs `body.ticket_subject[:80]`. While truncated, this means ticket subjects (which may contain PII like employee names, device serial numbers, or issue descriptions) are written to log files.

**Recommendation:** In production, consider logging only a hash of the subject or omitting it entirely. Ensure log files have appropriate access controls.

### L2. `cors_origin` Default Is a Placeholder

**File:** `backend/app/config.py:17`
**Severity:** Low
**Exploitability:** Low

The default `cors_origin` is `chrome-extension://placeholder`. If someone deploys without setting this in `.env`, CORS will reject all requests (safe failure). The validator at line 60-82 correctly rejects `*` with a token. Good defense-in-depth.

**Recommendation:** No action needed. Consider adding a startup warning if the origin still contains "placeholder".

### L3. Content Script Runs on Broad URL Patterns

**File:** `extension/public/manifest.json:20-28`
**Severity:** Low
**Exploitability:** Very low

The content script matches patterns like `*://*/*/helpdesk/WebObjects/Helpdesk.woa/*` and `*://*/*ticketDetail*`. While specific enough for WHD, the `*://*/*ticketDetail*` pattern could match URLs on unrelated sites. The content script itself only reads DOM data and doesn't transmit it externally (only via `chrome.runtime.sendMessage` to the extension's own sidebar).

**Recommendation:** If possible, narrow the match patterns to include the specific WHD hostname. For flexibility (different customers have different hostnames), the current broad patterns are acceptable.

### L4. No Content Security Policy in Extension Manifest

**File:** `extension/public/manifest.json`
**Severity:** Low
**Exploitability:** Very low (MV3 has strong default CSP)

The manifest does not declare an explicit `content_security_policy`. Manifest V3 enforces a strong default CSP: `script-src 'self'; object-src 'self'`. This is actually fine — the default is secure. Adding an explicit CSP would be defense-in-depth documentation.

**Recommendation:** Optionally add the CSP explicitly in the manifest to document the security boundary: `"content_security_policy": { "extension_pages": "script-src 'self'; object-src 'self'" }`.

### L5. Version Mismatch Between Backend and Extension

**File:** `backend/app/config.py:19` (version: `1.8.0`), `backend/pyproject.toml:3` (version: `1.11.0`), `extension/public/manifest.json:4` (version: `1.11.0`), `extension/package.json:3` (version: `1.8.0`)
**Severity:** Low (informational)

There are version inconsistencies across files. The `config.py` hardcoded version and `package.json` version are behind the manifest and pyproject versions.

**Recommendation:** Centralize version management or add a CI check that verifies all version strings match.

### L6. Release Workflow Uses `pip download` Without Hash Checking

**File:** `.github/workflows/release.yml:136`
**Severity:** Low
**Exploitability:** Very low (GitHub Actions environment)

The release workflow downloads Python wheels via `pip download` without `--require-hashes`. While the Ollama, uv, NSSM, and Python downloads all have SHA256 verification, the backend's Python dependencies are downloaded without hash pinning.

**Recommendation:** Generate a `requirements.txt` with hashes (`pip-compile --generate-hashes`) or use `uv pip compile --generate-hashes` to pin all dependency hashes for supply chain protection.

### L7. Installer Uses `-ExecutionPolicy Bypass`

**File:** `installer/setup.iss:102, 107, 110, etc.`
**Severity:** Low
**Exploitability:** Very low (installer context)

PowerShell scripts in the installer use `-ExecutionPolicy Bypass`. This is standard practice for installers (the scripts are bundled and known-good), but it means the scripts will run regardless of the system's PowerShell execution policy.

**Recommendation:** No action needed for this deployment model. Document in security docs that the installer requires PowerShell execution.

### L8. No Audit Logging for Administrative Actions

**File:** Various routers
**Severity:** Low
**Exploitability:** N/A

There is no dedicated audit trail for security-sensitive actions: login attempts, session creation/destruction, article deletion, collection clearing, shutdown commands. Standard application logging captures some of this (e.g., auth failures at `security.py:127`), but there's no structured audit log.

**Recommendation:** For production, add a dedicated audit logger that records: timestamp, action, client IP, success/failure, and session/token info. Write to a separate audit log file with restricted permissions.

### L9. `httpx.Client` Instances Not Shared

**File:** `backend/app/services/llm_service.py:21`, `backend/app/services/embed_service.py:24`, `backend/app/services/microsoft_docs.py:73`
**Severity:** Informational
**Exploitability:** N/A

New `httpx.Client` instances are created in service constructors, and service instances are created per-request in the generate endpoint. This means TCP connection pooling is not reused across requests. While not a security issue, it increases the risk of socket exhaustion under load.

**Recommendation:** Consider using a singleton or request-scoped shared client via FastAPI dependency injection.

### L10. No Input Sanitization on `prompt_suffix`

**File:** `backend/app/routers/generate.py:95-96`
**Severity:** Low
**Exploitability:** Low (requires authenticated access)

The `prompt_suffix` field (max 2000 chars) is appended directly to the LLM prompt. While this is by design (custom instructions), it provides a direct prompt injection vector for authenticated users.

**Recommendation:** Since this field is explicitly for user-provided instructions and the user is authenticated, this is by design. Consider adding a note in the UI that this field is for internal use only.

## What's Done Well

1. **SSRF Prevention** (`backend/ingestion/url_loader.py`): Comprehensive SSRF blocking with DNS resolution checking, private IP range blocking, IPv4-mapped IPv6 detection, redirect re-validation at each hop. This is textbook-quality SSRF prevention.

2. **Constant-Time Token Comparison** (`backend/app/middleware/security.py:111`, `backend/app/routers/auth.py:116-117`): Uses `secrets.compare_digest()` throughout, preventing timing-based token extraction.

3. **CORS Configuration** (`backend/app/config.py:60-82`): The validator that rejects `CORS_ORIGIN=*` with `API_TOKEN` set is excellent defense-in-depth. CORS is locked to the specific extension origin.

4. **Input Validation** (`backend/app/models/request_models.py`): Thorough Pydantic validation with explicit field length limits, custom field key/value limits, control character stripping, tag validation, and type-safe Literal rating values.

5. **Security Headers** (`backend/app/middleware/security.py:352-381`): X-Content-Type-Options, X-Frame-Options, Cache-Control, Referrer-Policy all set correctly. Server header stripped.

6. **HttpOnly Session Cookies** (`backend/app/routers/auth.py:128-136`): SameSite=Strict, HttpOnly, path-scoped. Session IDs generated with `secrets.token_urlsafe(32)` (256 bits of entropy).

7. **File Upload Security** (`backend/app/routers/ingest.py`): Filename sanitization via `PurePosixPath.name`, extension allowlist, streaming size limits, temp file cleanup with retry for Windows AV locks, upload semaphore for concurrency control.

8. **Rate Limiting** (`backend/app/middleware/security.py:143-241`): Per-path, per-IP rate limiting with configurable limits, memory management via periodic sweep, detailed documentation about proxy deployment considerations.

9. **Request Size Limiting** (`backend/app/middleware/security.py:249-343`): Both Content-Length header check and streaming body check. Exempt paths for file uploads. Proper body replay for the downstream app.

10. **Secret Storage Separation** (`extension/src/shared/constants.ts:60-64`): API token stored in `chrome.storage.local` (never synced to other devices), while settings use `chrome.storage.sync`. Correct separation of secrets from preferences.

11. **Pure ASGI Middleware** (`backend/app/middleware/security.py`): All middleware is pure ASGI `__call__` — no BaseHTTPMiddleware overhead, streaming-safe, no body buffering. This is the correct approach for FastAPI production deployments.

12. **Structured JSON Logging** (`backend/app/logging_config.py`): Consistent JSON format with timestamps, silenced noisy library loggers. Good foundation for log aggregation.

13. **SHA256 Verification in CI** (`.github/workflows/release.yml`): Ollama, uv, and NSSM downloads all have SHA256 hash verification. Pinned versions prevent supply chain drift.

14. **Minimal Extension Permissions** (`extension/public/manifest.json:6-14`): Only `sidePanel`, `storage`, `activeTab`, `nativeMessaging`. Host permissions limited to `http://localhost:8765/*`. No broad host access.

15. **Management SPA Uses `encodeURIComponent`** (`extension/src/management/api.ts:81, 85, 122, 129`): All dynamic path parameters are properly URL-encoded, preventing path traversal via API client.

## Brainstorm: Security Enhancements

### Short-Term (Before Multi-User Deployment)

1. **Audit Logging**: Add a structured audit log for security-sensitive actions (login, logout, article delete, collection clear, shutdown). Write to a separate file with rotation.

2. **Session Persistence**: Store sessions in SQLite or a file to survive restarts. Add a config flag `SESSION_BACKEND=memory|sqlite`.

3. **CSRF Token**: Add double-submit cookie CSRF protection to the management SPA's state-changing endpoints.

4. **Health Endpoint Scoping**: Return minimal info for unauthenticated `/health` calls; detailed info behind auth.

5. **Prompt Injection Mitigation**: Wrap user-supplied content in XML delimiter tags (e.g., `<user_ticket>...</user_ticket>`) in the prompt template to make injection boundaries clearer to the LLM.

### Medium-Term

6. **Request Signing**: Add HMAC request signing between the extension and backend to prevent replay attacks (currently the static token is replayable indefinitely).

7. **Token Rotation**: Add a `POST /auth/rotate-token` endpoint to generate a new API token and update the `.env` file. Add scheduled rotation reminders.

8. **Dependency Hash Pinning**: Use `uv pip compile --generate-hashes` to pin all Python dependency hashes in the release workflow.

9. **Content Security Policy Headers**: Add CSP headers to the `/manage` SPA responses: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'`.

10. **IP Allowlisting**: Add an optional `ALLOWED_CLIENT_IPS` config setting for network-exposed deployments to restrict API access to known client IPs.

### Long-Term

11. **TLS Support**: Add optional HTTPS via uvicorn's `--ssl-certfile`/`--ssl-keyfile` for deployments beyond localhost. Flip `secure=True` on session cookies when TLS is active.

12. **Role-Based Access Control**: If the tool grows to support multiple user roles (technician vs. admin), add RBAC to protect destructive operations (collection clear, shutdown) from non-admin sessions.

13. **Anomaly Detection**: Log and alert on unusual patterns: excessive failed auth attempts, unusual request volumes, requests to nonexistent endpoints (404 spikes).

14. **Secrets Manager Integration**: For enterprise deployment, support reading `API_TOKEN` from Windows Credential Manager or Azure Key Vault instead of `.env` files.

15. **Penetration Testing**: Before wider rollout, consider a focused pentest on the backend API, especially the ingestion endpoints (file upload + URL fetch) and the LLM prompt construction.
