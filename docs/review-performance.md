# Performance Review

## Executive Summary

The application is architecturally sound for a local single-user deployment but has several performance bottlenecks that will compound under multi-user production load. The most critical issues are: (1) new HTTP client and service instances created per request, wasting connection setup time and preventing connection reuse; (2) synchronous httpx clients wrapped in `asyncio.to_thread` where native async httpx would eliminate thread-pool contention; and (3) the global asyncio.Lock in the rate limiter serializing all rate-limited requests. The frontend is well-structured with Zustand selector-level subscriptions preventing most unnecessary re-renders, though the content script MutationObserver and health polling could be tightened.

## Critical Issues

### C1. New HTTP clients created per request — no connection pooling (HIGH impact)

**Files:** `backend/app/services/llm_service.py:20`, `backend/app/services/embed_service.py:24`, `backend/app/services/microsoft_docs.py:73-77`, `backend/app/routers/health.py:36`, `backend/app/routers/models.py:15`

Every request to `/generate` instantiates a new `LLMService()`, `EmbedService()`, `RAGService()`, and `MicrosoftDocsService()` (see `generate.py:28-30`). Each of these creates its own `httpx.Client()` with a fresh TCP connection pool. For `LLMService` and `EmbedService`, these are synchronous clients that open and maintain separate connection pools to the same Ollama host.

Additionally, the `/health` endpoint (`health.py:36`) and `/models` endpoint (`models.py:15`) create throwaway `httpx.AsyncClient()` instances inside `async with` blocks on every call. This means every 5-second health poll from the sidebar opens a new TCP connection, does the TLS/HTTP handshake (even over localhost), gets the response, and tears down the connection.

**Impact:** Under multi-user load (e.g., 5 users generating simultaneously), you get 5x LLM clients + 5x embed clients + 5x MS Docs clients + N health-check clients — none sharing connections. This wastes OS sockets, increases latency by ~2-10ms per request for connection setup, and can exhaust the default thread pool (40 threads in Python) since each `to_thread` call holds a thread with its own client.

**Fix:** Create singleton service instances in the app lifespan and store them on `app.state`. Use a shared `httpx.AsyncClient` for Ollama communication (replacing the sync client + `to_thread` pattern entirely).

### C2. Synchronous HTTP clients + `to_thread` instead of native async (HIGH impact)

**Files:** `backend/app/services/llm_service.py:20,27`, `backend/app/services/embed_service.py:24,36`, `backend/app/services/microsoft_docs.py:73,105-110`

`LLMService._generate_sync` and `EmbedService._embed_sync` use synchronous `httpx.Client` and run via `asyncio.to_thread()`. This means every LLM generation and every embedding call occupies a thread from the default executor (usually 40 threads max). A single `/generate` request can consume 3+ threads simultaneously:
- 1 thread for LLM generation (blocks for 5-30 seconds with a 14B model)
- 1 thread for the RAG embedding query
- Up to 3 threads for MS Docs article fetches (`microsoft_docs.py:110`)

With 5 concurrent users, that is potentially 25+ threads blocked on I/O, approaching or exceeding the default pool size.

**Impact:** Thread pool exhaustion causes queuing and increased latency for all users. LLM calls to Ollama (which can take 10-30 seconds for a 14B model) hold threads idle during I/O.

**Fix:** Replace synchronous `httpx.Client` with `httpx.AsyncClient` across all services. This eliminates `to_thread` overhead entirely for HTTP I/O and frees the thread pool for actual CPU-bound work (ChromaDB queries are legitimately blocking since the ChromaDB Python client is synchronous).

### C3. Rate limiter global lock serializes all rate-limited requests (MEDIUM-HIGH impact)

**File:** `backend/app/middleware/security.py:219`

The `RateLimitMiddleware` uses a single `asyncio.Lock` for all rate-limited paths. Every request to `/generate`, `/ingest/upload`, `/ingest/url`, or `/feedback` must acquire this lock, perform timestamp list operations, and release it. While each critical section is fast (microseconds), under high concurrency the lock creates a serialization point.

More importantly, `_evict_stale_entries()` at line 187 iterates all keys in `_counts` during the sweep, which runs once per 60-second window. If many distinct IPs have hit the server, this sweep blocks all other rate-limit checks.

**Impact:** Under moderate load (10+ concurrent requests), the lock contention adds measurable latency. The sweep operation can cause latency spikes proportional to the number of tracked IPs.

**Fix:** Consider a lock-free sliding window approach, or partition locks by path+IP hash to reduce contention. For the sweep, run it as a background task instead of inline.

### C4. KB article index loads ALL chunks into memory on cache miss (MEDIUM-HIGH impact)

**File:** `backend/app/routers/kb.py:132-133`

When the article cache expires (every 5 minutes), `_get_article_index` calls `col.get(include=["metadatas"])` with no filters, which loads ALL chunk metadata from ChromaDB into Python memory. For a KB with 1000 articles averaging 5 chunks each, this is 5000 metadata dicts loaded and processed.

The lock at line 117 means only one coroutine rebuilds the cache, but all other requests to `/kb/articles`, `/kb/stats`, or `/kb/tags` block on this lock during the rebuild.

**Impact:** Cache rebuild latency grows linearly with KB size. With 10,000+ chunks, this could take 500ms-2s, during which all KB management endpoints stall.

**Fix:** Consider incremental cache updates (only fetch metadata modified since last cache build, if ChromaDB supports it) or background cache refresh that doesn't block request handling.

## Improvement Opportunities

### I1. Ingestion pipeline embeds one chunk at a time — no batching (MEDIUM impact)

**File:** `backend/ingestion/pipeline.py:139-140`

The `_upsert_stream` method calls `self._do_embed(text)` for each chunk individually. For a document with 20 chunks, this means 20 sequential HTTP calls to Ollama's `/api/embeddings` endpoint. The Ollama embedding API supports only single-text requests, but the pipeline could batch multiple texts and use `asyncio.gather` (if converted to async) or thread-pool parallelism to embed multiple chunks concurrently.

**Impact:** Ingestion of a 20-chunk document takes ~20x the latency of a single embedding call (typically 100-300ms each = 2-6 seconds total). Parallel embedding could reduce this to ~1-2 seconds.

**Fix:** Run embedding calls in parallel using a thread pool or async gather, with a concurrency limit (e.g., 4 concurrent embeds).

### I2. `_embed` fallback creates a new httpx.Client per call (MEDIUM impact)

**File:** `backend/ingestion/pipeline.py:180-181`

The fallback `_embed` method (used when no custom `embed_fn` is injected) creates a new `httpx.Client()` inside a `with` block for every single embedding. This is called once per chunk during ingestion.

**Impact:** For a 20-chunk document, this opens and closes 20 TCP connections. Combined with I1, this is the slowest possible pattern for ingestion.

**Fix:** Use the injected `embed_fn` (which reuses a persistent client) consistently, or make the fallback client a class attribute.

### I3. Health check creates a new AsyncClient on every poll (LOW-MEDIUM impact)

**Files:** `backend/app/routers/health.py:36`, `backend/app/routers/models.py:15`

The `/health` endpoint creates a new `httpx.AsyncClient()` per request. The sidebar polls this every 5 seconds, and the KnowledgePanel polls it every 10 seconds. That is up to 12 new TCP connections per minute per user just for health checks.

**Fix:** Use a shared async client stored on `app.state`.

### I4. MutationObserver watches entire document subtree (LOW-MEDIUM impact)

**File:** `extension/src/content/sidebar-host.ts:47-52`

The MutationObserver falls back to watching `document.body` with `subtree: true` and `childList: true` when `#ticketDetailForm` is not found. On a complex WHD page with many DOM elements, this triggers the callback on every DOM mutation, including ones completely unrelated to ticket data (e.g., animations, ads, other scripts). The 300ms debounce helps, but the callback itself still fires for every mutation.

**Impact:** On complex pages, this can cause stuttering if mutations are frequent, as each mutation schedules and cancels timeouts repeatedly.

**Fix:** Narrow the observer target. If `#ticketDetailForm` is not found, try a more specific ancestor (e.g., the main content area) rather than `document.body`. Also consider adding `attributeFilter` to ignore irrelevant mutations.

### I5. Frontend health poll does not back off when backend is offline (LOW impact)

**File:** `extension/src/sidebar/components/BackendControl.tsx:138-147`

The `BackendControl` component polls the backend health every 5 seconds regardless of whether it's online or offline. When the backend is down, every poll results in a connection refused error after a 4-second timeout (`AbortSignal.timeout(4000)` in `api-client.ts:51`).

**Impact:** When offline, the sidebar makes a failing HTTP request every 5 seconds, each potentially blocking for up to 4 seconds. This wastes resources and can make the sidebar feel sluggish.

**Fix:** Implement exponential backoff — poll every 5s when online, 15s/30s/60s when offline.

### I6. `storage.saveSettings` reads current settings before every write (LOW impact)

**File:** `extension/src/lib/storage.ts:23-24`

Every `saveSettings` call first reads the full current settings from `chrome.storage.sync`, then merges the partial update, then writes back. This means a settings update requires two async chrome.storage operations.

**Impact:** Minimal for normal usage (settings change rarely), but could cause race conditions if two rapid settings updates overlap.

**Fix:** Use `chrome.storage.sync.get` + `chrome.storage.sync.set` atomically, or just write the full merged settings object from the Zustand store directly.

### I7. Pinned articles fetched sequentially in generate endpoint (LOW impact)

**File:** `backend/app/routers/generate.py:255-269`

The `_fetch_pinned_articles` function fetches each pinned article one at a time in a loop with `await asyncio.to_thread(col.get, ...)` per article. With the maximum 10 pinned articles, this is 10 sequential ChromaDB queries.

**Impact:** Adds ~10-50ms per pinned article (depends on ChromaDB performance). Worst case with 10 pins = 100-500ms of sequential I/O.

**Fix:** Use `asyncio.gather` to fetch all pinned articles in parallel.

### I8. Two-phase RAG with category filter can make 3 sequential ChromaDB queries (LOW impact)

**File:** `backend/app/services/rag_service.py:38-72`

When a category is provided, the RAG service runs a filtered KB query + ticket query in parallel (good), but then potentially runs a third unfiltered query sequentially at line 58. This third query is only triggered when the filtered results are insufficient, but when it happens, it adds latency.

**Fix:** Run the unfiltered query speculatively in the initial `gather` and discard if not needed.

### I9. No code splitting in sidebar build (LOW impact)

**File:** `extension/vite.config.ts:22-24`

The Vite config outputs all shared chunks to `chunks/[name]-[hash].js`, but there's no explicit code splitting configuration. The sidebar, options page, and service worker all share the same chunk pool, which means the sidebar bundle includes code for all entry points.

However, for a browser extension sidebar this is generally acceptable — the sidebar is loaded once and stays in memory. The content script is correctly built as a separate IIFE. The management SPA has its own build config with separate output.

**Impact:** Low. The sidebar bundle might be slightly larger than necessary, but it loads once and stays in memory. React 18 + Zustand + Radix UI is a reasonable dependency set.

### I10. Repeated `EmbedService()` instantiation in generate path (LOW impact)

**File:** `backend/app/routers/generate.py:138`

The dynamic few-shot retrieval (`_get_dynamic_examples`) creates its own `EmbedService()` instance at line 138, separate from the one already created inside `RAGService.__init__` at `rag_service.py:22`. This means two separate Ollama HTTP clients for embedding in the same request.

**Fix:** Pass the existing embed service through, or use a singleton.

## Architecture Observations

### Well-done patterns worth maintaining

1. **Pure ASGI middleware** (`security.py`): All four middleware classes are implemented as raw ASGI callables (not `BaseHTTPMiddleware`), which avoids the body-buffering overhead and is streaming-safe. This is the correct approach for production.

2. **Zustand selector-level subscriptions** (`sidebarStore.ts`): The sidebar components use individual selectors like `useSidebarStore((s) => s.reply)` rather than consuming the whole store. This means only components that use a specific slice of state re-render when that slice changes. This is textbook-correct Zustand usage and prevents cascade re-renders.

3. **Debounced MutationObserver** (`sidebar-host.ts:41-44`): The 300ms debounce prevents flooding the message channel during rapid DOM mutations. Combined with the targeted observer on `#ticketDetailForm` (when available), this is a good balance.

4. **Parallel RAG + web search** (`generate.py:42-49`): The `/generate` endpoint runs RAG retrieval and Microsoft Learn search in parallel via `asyncio.gather`. This is the correct pattern — the two operations are independent and the slower one (web search) can proceed while RAG completes.

5. **Upload semaphore** (`shared.py:6`): The `asyncio.Semaphore(1)` ensures only one ingestion runs at a time, preventing ChromaDB write contention and Ollama embedding overload. This is appropriate for a single-backend deployment.

6. **IIFE content script build** (`vite.config.content.ts`): Correctly builds the content script as IIFE since MV3 content scripts don't support ES modules. The `inlineDynamicImports: true` ensures the lazy `import('./dom-inserter')` and `import('./sidebar-host')` are inlined.

7. **Session store with async lock** (`auth.py:41-82`): The in-memory session store uses `asyncio.Lock` for thread safety and sweeps expired sessions during `create()`. This is simple, correct, and appropriate for a single-process deployment.

8. **Structured JSON logging** (`logging_config.py`): JSON-formatted logs with timestamps, levels, and exception info. Combined with quieted library loggers (uvicorn.access, chromadb, httpx), this keeps log output clean and machine-parseable.

9. **SSRF prevention with redirect validation** (`url_loader.py:56-73, 113-158`): The URL loader validates every redirect hop against private IP ranges, including IPv4-mapped IPv6 addresses. This is a thorough SSRF defense.

10. **Request abort support** (`useGenerateReply.ts:23, api-client.ts:39`): The sidebar passes an `AbortController.signal` to the fetch call and handles `AbortError` gracefully. Users can cancel long-running LLM generations without waiting.

## Brainstorm: Performance Enhancements

### B1. Singleton service instances with shared connection pools

Create `LLMService`, `EmbedService`, and `MicrosoftDocsService` once during app lifespan and store them on `app.state`. Replace synchronous `httpx.Client` with `httpx.AsyncClient` configured with connection pooling (`max_connections=10, max_keepalive_connections=5`). This single change addresses C1, C2, I2, I3, and I10 simultaneously.

```python
# In lifespan:
app.state.ollama_client = httpx.AsyncClient(
    base_url=settings.ollama_base_url,
    timeout=120.0,
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)
app.state.llm_service = LLMService(app.state.ollama_client)
app.state.embed_service = EmbedService(app.state.ollama_client)
```

### B2. Streaming LLM responses to the frontend

Currently the LLM service uses `"stream": False` and waits for the full response before returning. Ollama supports streaming via `"stream": True`, returning tokens incrementally. The frontend already has the UI structure to display incremental text (the reply box with `aria-live="polite"`).

Streaming would:
- Reduce perceived latency from 10-30s to <1s (first token appears immediately)
- Allow users to see partial results and cancel earlier
- Free the backend thread/connection sooner (stream can be forwarded via SSE)

Implementation: Use FastAPI `StreamingResponse` with SSE, connect to Ollama's streaming endpoint, forward tokens to the frontend via `EventSource` or chunked fetch.

### B3. Embedding result cache for RAG queries

Ticket queries that are similar (e.g., same subject/description) produce similar embeddings. A short-lived cache (30-60 seconds) on embedding results would prevent re-embedding the same query text when a user regenerates a reply or when multiple users submit tickets with similar subjects.

The Microsoft Docs service already has this pattern (`microsoft_docs.py:39-66`). Apply the same approach to `EmbedService.embed()`.

### B4. Precomputed article index with change tracking

Instead of rebuilding the full article index every 5 minutes from a full ChromaDB scan (C4), maintain a persistent index that updates incrementally:
- After each mutation (create/update/delete article), update only the affected entries
- Use a version counter or hash to detect external changes (e.g., CLI ingestion)
- Store the index in a lightweight SQLite DB or just a JSON file for crash recovery

### B5. Background cache warming on startup

Pre-warm the article index cache, ChromaDB collection handles, and Ollama model loading during the lifespan startup. Currently, the first request after startup pays the cost of:
- Building the article index (C4)
- Loading the Ollama model into GPU memory (can take 5-15 seconds for 14B)
- ChromaDB collection handle creation

A startup warm-up task could call `RAGService.retrieve("warmup", max_docs=1)` and `LLMService.generate("Hello", model)` with a trivial prompt to pre-load everything.

### B6. Frontend: Conditional polling with visibility API

Use `document.visibilityState` and the `visibilitychange` event to pause health polling when the sidebar is not visible (e.g., user switched tabs or minimized). Resume polling when the sidebar becomes visible again. This reduces unnecessary network requests and is a standard browser optimization.

```typescript
// In BackendControl:
useEffect(() => {
  const handler = () => {
    if (document.visibilityState === 'visible') schedulePoll(0) // immediate
    else clearTimer()
  }
  document.addEventListener('visibilitychange', handler)
  return () => document.removeEventListener('visibilitychange', handler)
}, [schedulePoll, clearTimer])
```

### B7. Lazy-load KnowledgePanel and management components

The `KnowledgePanel` component starts polling on mount even when collapsed (it fetches doc counts). Consider delaying the initial fetch until the panel is expanded, and stopping the poll when collapsed.

Similarly, the management SPA imports `@tanstack/react-query` which adds ~15KB gzipped. Since the management SPA is served separately at `/manage`, this doesn't affect sidebar bundle size, but the sidebar's `ManageTab` component could be lazy-loaded since users rarely access it.

### B8. ChromaDB query result caching for repeated searches

If the same KB search is performed within a short window (e.g., user regenerates a reply without changing ticket data), cache the ChromaDB query results for 30-60 seconds. Key the cache on the embedding vector hash + collection name + n_results.

### B9. Batch ChromaDB operations for pinned articles

Replace the sequential per-article `col.get(where={"article_id": aid})` loop in `_fetch_pinned_articles` with a single batch query using ChromaDB's `$in` operator:

```python
col.get(
    where={"article_id": {"$in": article_ids}},
    include=["documents", "metadatas"],
)
```

Then group the results by article_id in Python. This turns N queries into 1.

### B10. Content script: targeted DOM observation with attribute filters

Instead of watching the entire `document.body` subtree, use multiple targeted observers:
- One for the ticket detail form (existing)
- One for the status select element
- One for the notes section

Each observer watches only its relevant DOM subtree with `attributeFilter` set to relevant attributes (e.g., `['value', 'selected']`). This dramatically reduces the number of mutation callbacks.
