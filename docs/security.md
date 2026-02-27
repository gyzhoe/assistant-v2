# Security Guide — AI Helpdesk Assistant

## Overview

This system is designed for enterprise on-premises deployment. All AI inference is local;
no ticket data is sent to external services. This document describes the security controls
in place and the steps required to harden the deployment.

---

## Controls Summary

| Control | Status | Notes |
|---|---|---|
| All inference local | Enforced | Ollama only — no cloud calls anywhere in the codebase |
| CORS restricted to extension origin | Enforced | `CORSMiddleware` locks to `chrome-extension://<ID>` |
| API token auth | Configurable | Set `API_TOKEN` in `.env` — required in production |
| Request size limit | Enforced | Default 64 KB for API; 50 MB for file uploads (`MAX_UPLOAD_BYTES`) |
| Rate limiting | Enforced | 20 req/min for `/generate`; 5 req/min for `/ingest/upload` |
| Upload concurrency | Enforced | Single concurrent upload via `asyncio.Semaphore(1)`; 409 on conflict |
| Filename sanitization | Enforced | `PurePosixPath(filename).name` strips directory traversal |
| File type allowlist | Enforced | Only `.json`, `.csv`, `.html`, `.htm`, `.pdf` accepted |
| Input length caps | Enforced | Pydantic `max_length` on all fields; prevents prompt injection via oversized input |
| Security headers | Enforced | `X-Content-Type-Options`, `X-Frame-Options`, `Cache-Control: no-store`, `Referrer-Policy` |
| No secrets in code | Enforced | `.env` gitignored; all config via `pydantic-settings` |
| Content script XSS | Enforced | No `eval()`, no `innerHTML` with untrusted content |
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

Consider a Windows service (NSSM) or Task Scheduler to auto-start the backend.

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

### 6. Ollama Hardening

Ensure Ollama is also bound to localhost:
```
# Edit Ollama service to set OLLAMA_HOST=127.0.0.1:11434
```

Ollama has no built-in authentication. The FastAPI backend is the only component
that should call Ollama.

### 7. Audit Logging (optional enhancement)

The backend does not currently log ticket contents (by design — to minimize data exposure).
If your security policy requires audit logs, add structured logging middleware that records:
- Timestamp, client IP, endpoint called, model used, latency
- Do NOT log ticket subject/description

---

## Threat Model

| Threat | Mitigation |
|---|---|
| Malicious local process calling the backend | API token header (`X-Extension-Token`) |
| Oversized payload to Ollama (DoS) | Request size limit (64 KB API, 50 MB upload), input `max_length` |
| Rate abuse (runaway extension) | Rate limiting (20 req/min generate, 5 req/min upload) |
| Concurrent upload exhaustion | Semaphore limits to 1 active ingestion; 409 on conflict |
| Path traversal via filename | Filename sanitized with `PurePosixPath().name` |
| Malicious file type upload | Extension allowlist: `.json`, `.csv`, `.html`, `.htm`, `.pdf` only |
| Ticket data leak via prompt injection | Input truncation, no external calls |
| Ticket data leak via browser extension | Extension only stores data in memory; nothing persisted to cloud |
| Unauthorized extension calling backend | CORS + API token combination |
| Server identity leak | Security headers strip server banner |

---

## What This System Does NOT Do

- Does not send data to OpenAI, Anthropic, or any cloud service
- Does not store ticket content to disk (only embeddings of ingested KB/past tickets)
- Does not log ticket content
- Does not require network access beyond localhost
