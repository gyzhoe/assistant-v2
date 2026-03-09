# Security Guide — AI Helpdesk Assistant

## Overview

This system is designed for enterprise on-premises deployment. All AI inference is local;
no ticket data is sent to external services. This document describes the security controls
in place and the steps required to harden the deployment.

---

## Controls Summary

| Control | Status | Notes |
|---|---|---|
| All inference local | Enforced | llama-server (llama.cpp) only — no cloud calls for inference. Optional Microsoft Learn search is read-only documentation lookup |
| CORS restricted to extension origin | Enforced | `CORSMiddleware` locks to `chrome-extension://<ID>` |
| API token auth | Configurable | Set `API_TOKEN` in `.env` — required in production |
| Request size limit | Enforced | Default 64 KB for API; 50 MB for file uploads (`MAX_UPLOAD_BYTES`) |
| Rate limiting | Enforced | 20 req/min for `/generate`; 5 req/min for `/ingest/upload` and `/ingest/url` |
| Ingestion concurrency | Enforced | Single concurrent ingestion (upload or URL) via `asyncio.Semaphore(1)`; 409 on conflict |
| URL ingestion SSRF prevention | Enforced | Private IP blocking, DNS pre-resolution, redirect re-validation, scheme/content-type whitelist |
| Microsoft Learn domain lock | Enforced | Only articles from `learn.microsoft.com` are fetched; search keywords use only subject + category |
| Filename sanitization | Enforced | `PurePosixPath(filename).name` strips directory traversal |
| File type allowlist | Enforced | Only `.json`, `.csv`, `.html`, `.htm`, `.pdf` accepted |
| Input length caps | Enforced | Pydantic `max_length` on all fields; prevents prompt injection via oversized input |
| Security headers | Enforced | `X-Content-Type-Options`, `X-Frame-Options`, `Cache-Control: no-store`, `Referrer-Policy` |
| No secrets in code | Enforced | `.env` gitignored; all config via `pydantic-settings` |
| Content script XSS | Enforced | No `eval()`, no `innerHTML` with untrusted content |
| HttpOnly cookie sessions | Enforced | `whd_session` cookie (SameSite=Strict, 24h expiry) for KB Management SPA auth |
| CSRF protection | Enforced | State-changing endpoints require valid CSRF token; pure ASGI middleware |
| SHA-256 model verification | Enforced | GGUF model downloads verified against expected SHA-256 hash before use |
| Audit logging | Enforced | Structured JSON logging for login, logout, delete, shutdown — timestamp, client IP, outcome |
| Extension host permissions | Minimal | Only `http://localhost:8765/*` |

---

## Production Hardening Checklist

### 1. Configure the API Token (REQUIRED)

Generate a strong shared secret:
```bash
openssl rand -hex 32
```

Set it in `backend/.env`:
```
API_TOKEN=<generated-value>
```

The extension reads this from `chrome.storage.local` (under `apiToken`).
Configure it in the extension options page after deploying.

> **Why?** CORS alone doesn't protect a localhost HTTP server from other processes
> on the same machine calling it. The API token ensures only your extension can
> generate replies.

### 2. Set the Correct Extension Origin

After loading the unpacked extension in Edge, find its ID at `edge://extensions`.
Set it in `backend/.env`:
```
CORS_ORIGIN=chrome-extension://abcdefghijklmnopqrstuvwxyz123456
```

Restart the backend after changing this value.

### 3. Restrict Backend to Localhost Only

The backend should bind to `127.0.0.1` only — never `0.0.0.0` in production:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

The backend is auto-started by the native messaging host (`native_host.py`) when the extension connects. No separate service manager is needed.

### 4. Run as a Low-Privilege Service Account

On Windows, run the backend under a dedicated service account with:
- No internet access
- Read/write access to `chroma_data/` only
- No admin rights

### 5. ChromaDB Data Protection

ChromaDB stores embeddings of your ticket/KB content. Protect it:
- Store `chroma_data/` on an encrypted volume or use BitLocker
- Restrict file system permissions to the service account only
- Include in your backup rotation

### 6. LLM Server Hardening

Ensure llama-server is bound to localhost (the default):
```
llama-server --host 127.0.0.1 --port 11435 -m models/Qwen3.5-9B-Q4_K_M.gguf
llama-server --host 127.0.0.1 --port 11436 -m models/nomic-embed-text-v1.5.f16.gguf --embedding
```

llama-server has no built-in authentication. The FastAPI backend is the only component
that should call llama-server.

### 7. Audit Logging (Enforced)

The backend uses structured JSON audit logging for security-sensitive actions:
- Login/logout attempts (success and failure), delete operations, shutdown events
- Each log entry records: timestamp, client IP, endpoint, and outcome
- Ticket content is never logged (by design — to minimize data exposure)

---

## Threat Model

| Threat | Mitigation |
|---|---|
| Malicious local process calling the backend | API token header (`X-Extension-Token`) |
| Oversized payload to LLM server (DoS) | Request size limit (64 KB API, 50 MB upload), input `max_length` |
| Rate abuse (runaway extension) | Rate limiting (20 req/min generate, 5 req/min upload) |
| Concurrent upload exhaustion | Semaphore limits to 1 active ingestion; 409 on conflict |
| Path traversal via filename | Filename sanitized with `PurePosixPath().name` |
| Malicious file type upload | Extension allowlist: `.json`, `.csv`, `.html`, `.htm`, `.pdf` only |
| SSRF via URL ingestion | DNS pre-resolution, private IP blocking (IPv4/IPv6/mapped), redirect re-validation per hop, scheme whitelist |
| SSRF via MS Learn search results | Domain validation: only `learn.microsoft.com` URLs fetched, 2 MB cap, 10s timeout |
| Ticket data leak via prompt injection | Input truncation; MS Learn search uses only subject + category (never full description) |
| Ticket data leak via browser extension | Extension only stores data in memory; nothing persisted to cloud |
| Unauthorized extension calling backend | CORS + API token combination |
| Session hijacking (cookie theft) | HttpOnly + SameSite=Strict + 24h expiry; periodic sweep of expired sessions |
| CSRF on state-changing endpoints | CSRF token validation on all POST/PUT/DELETE routes; pure ASGI middleware |
| Tampered model download | SHA-256 hash verification on all GGUF model downloads before use |
| Server identity leak | Security headers strip server banner |

---

---

## URL Ingestion SSRF Prevention

The `POST /ingest/url` endpoint accepts arbitrary URLs. The following measures prevent Server-Side Request Forgery:

1. **Scheme whitelist**: Only `http` and `https` schemes are allowed
2. **DNS pre-resolution**: The hostname is resolved via `socket.getaddrinfo()` before connecting
3. **Private IP blocking**: All resolved addresses are checked against RFC 1918/4193 ranges:
   - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (IPv4 private)
   - `127.0.0.0/8` (loopback), `169.254.0.0/16` (link-local)
   - `::1` (IPv6 loopback), `fe80::/10` (IPv6 link-local)
   - IPv4-mapped IPv6 addresses (`::ffff:127.0.0.1`) are unpacked and re-checked
4. **Redirect re-validation**: Redirects are followed manually (max 10 hops), with full SSRF validation on every intermediate URL
5. **Content-Type whitelist**: Only `text/html`, `text/plain`, `application/xhtml+xml`
6. **Response size cap**: 5 MB maximum
7. **Timeout**: 10 seconds per request

## Microsoft Learn Search Privacy

The optional Microsoft Learn integration searches public documentation at generation time:

- Search keywords use **only** ticket subject + category — never the full description
- Only articles hosted on `learn.microsoft.com` are fetched (domain validated via `urlparse`)
- Article content is capped at 3000 chars and cached for 5 minutes
- If the search fails, generation continues with local context only
- Disable entirely via `microsoft_docs_enabled = false` in `.env` or `include_web_context: false` per request

---

## What This System Does NOT Do

- Does not send data to any cloud service for inference (llama-server runs entirely locally)
- Does not store ticket content to disk (only embeddings of ingested KB/past tickets)
- Does not log ticket content
- Does not require internet access (Microsoft Learn search is optional and degrades gracefully)
