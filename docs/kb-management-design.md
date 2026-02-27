# KB Management Page — Design Specification

> Produced by team brainstorm (2026-02-27): Ursula (UX), Valentino (UI), Boris (Backend), Fiona (Frontend)

## Overview

Standalone web page at `http://localhost:8765/manage` for IT helpdesk admins to browse, search, import, and delete knowledge base articles. Built as a React SPA served by FastAPI's StaticFiles. Same-origin with the backend API — no CORS needed.

---

## Locked Decisions

| # | Decision | Answer |
|---|----------|--------|
| 1 | Layout | Single-column, max-width 960px, centered |
| 2 | Import flow | Collapsible section at bottom, triggered by header button with smooth scroll |
| 3 | Search | Substring title search + source type filter dropdown |
| 4 | Auth | `sessionStorage` + `X-Extension-Token` header (zero backend changes) |
| 5 | Serving | Static SPA via FastAPI `StaticFiles` at `/manage` |
| 6 | State mgmt | React Query (`@tanstack/react-query`) for server state |
| 7 | CSS sharing | Extract shared `tokens.css` from `sidebar.css`, no component reuse |
| 8 | Routing | No routing — single scrollable page |
| 9 | New deps | `@tanstack/react-query` + `@radix-ui/react-alert-dialog` only |
| 10 | Dark theme | Same `data-theme` toggle + shared token system |
| 11 | Collections | KB articles only in v1 (no ticket collection management) |
| 12 | Timestamps | `imported_at` (ISO 8601) added to chunk metadata during ingestion |

---

## Layout

```
+=========================================================================+
|  [AI] Knowledge Base Management              [+ Import] [theme toggle]  |
+=========================================================================+
|  +-----------+  +-----------+  +-----------+                            |
|  |    47     |  |   312     |  | [*] All   |                            |
|  | Articles  |  |  Parts    |  |  Online   |                            |
|  +-----------+  +-----------+  +-----------+                            |
+-------------------------------------------------------------------------+
|  [Search articles...]  [Source: All v]  [Sort: Recent v]                |
+-------------------------------------------------------------------------+
|  PDF   How to Reset AD Passwords       12 parts    2d ago              |
|        reset-ad.pdf                                                     |
+-------------------------------------------------------------------------+
|  URL   Configuring DHCP Scopes          8 parts    1w ago              |
|        learn.microsoft.com/...                                          |
+-------------------------------------------------------------------------+
|  v HTML VPN Troubleshooting Guide      15 parts    2w ago              |
|  +--- Detail --------------------------------------------------------+ |
|  | Source: vpn-guide.html (HTML)                                      | |
|  | Parts: 15  |  Imported: Feb 13, 2026                              | |
|  | Preview: "To troubleshoot VPN connectivity, first verify..."       | |
|  |                                              [Delete Article]      | |
|  +--------------------------------------------------------------------+ |
+-------------------------------------------------------------------------+
|  CSV   Printer Drivers Inventory       23 parts    3w ago              |
+-------------------------------------------------------------------------+
|  Showing 1-20 of 47          [< Prev]  1 2 3  [Next >]                |
+=========================================================================+
|  v IMPORT (collapsible section)                                         |
|  +--- Drop zone ---------------------------------------------------+   |
|  |  Drop files here or click to browse                              |   |
|  |  PDF, HTML, JSON, CSV — max 10MB each                           |   |
|  +------------------------------------------------------------------+   |
|  -- or import from URL --                                               |
|  [https://example.com/article        ] [Import URL]                    |
+=========================================================================+
```

---

## Backend API (MVP)

### New Endpoints

```
GET    /kb/articles?page=1&page_size=20&search=vpn&source_type=pdf
GET    /kb/articles/{article_id}
DELETE /kb/articles/{article_id}
GET    /kb/stats
```

### New Router: `app/routers/kb.py`

#### `GET /kb/articles`

List articles grouped by `article_id`, with pagination and filtering.

**Query params:** `page` (default 1), `page_size` (default 20), `search` (title substring), `source_type` (html|pdf|url|json|csv)

**Response:**
```json
{
  "articles": [
    {
      "article_id": "abc123...",
      "title": "How to Configure VPN",
      "source_type": "html",
      "source": "vpn-guide.html",
      "chunk_count": 5,
      "imported_at": "2026-02-15T10:30:00Z"
    }
  ],
  "total_articles": 42,
  "page": 1,
  "page_size": 20
}
```

**Implementation:** `col.get(include=["metadatas"])` → group by `article_id` in Python → server-side cache (5min TTL, invalidated on mutations) → paginate/filter on cached index.

#### `GET /kb/articles/{article_id}`

Article detail with all chunks.

**Response:**
```json
{
  "article_id": "abc123...",
  "title": "How to Configure VPN",
  "source_type": "html",
  "source": "vpn-guide.html",
  "chunk_count": 5,
  "imported_at": "2026-02-15T10:30:00Z",
  "chunks": [
    {
      "id": "chunk_sha256...",
      "text": "To configure the VPN client...",
      "section": "Installation",
      "metadata": {}
    }
  ]
}
```

**Implementation:** `col.get(where={"article_id": article_id}, include=["documents", "metadatas"])`

#### `DELETE /kb/articles/{article_id}`

Delete all chunks belonging to an article.

**Response:** `{"status": "ok", "chunks_deleted": 5}`

**Implementation:** `col.delete(where={"article_id": article_id})` — atomic, idempotent.

#### `GET /kb/stats`

Collection statistics for health dashboard.

**Response:**
```json
{
  "total_articles": 42,
  "total_chunks": 287,
  "by_source_type": { "html": 20, "pdf": 15, "url": 5, "manual": 2 }
}
```

### Existing Endpoints (reused as-is)

```
POST   /ingest/upload       (file import)
POST   /ingest/url          (URL import)
POST   /ingest/collections/{name}/clear  (clear collection)
GET    /health              (system status)
```

### Static Serving

```python
app.mount("/manage", StaticFiles(directory="static/manage", html=True), name="management")
```

### Performance

- Server-side article index cache (5min TTL) for `GET /kb/articles`
- Cache invalidated on any write operation (upload, delete, clear)
- Pagination on grouped article list, not raw chunks
- Lazy chunk loading: detail view calls targeted `col.get(where=...)` on demand

---

## Frontend Architecture

### Build

Third Vite config: `extension/vite.config.management.ts` → output to `backend/static/manage/`

```
"build:management": "vite build --config vite.config.management.ts"
```

### Component Tree

```
src/management/
  index.html              # Minimal HTML shell
  main.tsx                # React root + QueryClientProvider
  App.tsx                 # Layout shell, auth gate, toast container
  api.ts                  # Fetch wrapper (same-origin, X-Extension-Token)
  types.ts                # Management-specific types
  management.css          # Page-level styles
  components/
    Header.tsx            # Branding, import button, theme toggle
    StatCards.tsx          # Article count, parts count, system status
    ArticleList.tsx       # Search bar + filter + paginated table
    ArticleRow.tsx        # Single row: badge, title, parts, date, chevron
    ArticleDetail.tsx     # Expanded: source, preview, sections, delete
    ImportSection.tsx     # Collapsible file upload + URL import
    SearchBar.tsx         # Debounced input (300ms) with clear button
    SourceFilter.tsx      # Source type dropdown
    Pagination.tsx        # Page controls (20 per page)
    ConfirmDialog.tsx     # Radix AlertDialog for delete confirmation
    Toast.tsx             # Custom ~40 lines (role="status", aria-live="polite")
    EmptyState.tsx        # Zero-article CTA with import buttons
    TokenGate.tsx         # API token input form (shown on 401)
    SkeletonTable.tsx     # Shimmer loading rows
```

### State Management

**React Query** for server state:
- Article list: `useQuery(['articles', { page, search, sourceType }], ...)`
- Stats: `useQuery(['stats'], ...)` with 60s staleTime
- Delete: `useMutation` with `onSuccess` → invalidate articles + stats queries
- `keepPreviousData` for smooth pagination

**Local React state** for: expanded article ID, search input, selected filters, import section open/closed, API token.

### API Client (`src/management/api.ts`)

```ts
let token = ''
export function setToken(t: string) { token = t }

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { 'X-Extension-Token': token } : {}),
  }
  const resp = await fetch(path, { ...options, headers })
  if (!resp.ok) throw new ApiError(resp.status, await resp.json().catch(() => ({})))
  return resp.json() as Promise<T>
}
```

No `chrome.storage` dependency. Same-origin calls. `encodeURIComponent` on article IDs.

### Authentication

1. Page loads → `GET /kb/stats`
2. If no `API_TOKEN` configured → works immediately, no auth
3. If `API_TOKEN` configured → 401 → `TokenGate` shows password field
4. Admin enters token → stored in `sessionStorage` → included as `X-Extension-Token` header
5. Token survives page refresh, clears on tab close

### New Dependencies

| Package | Size | Justification |
|---------|------|---------------|
| `@tanstack/react-query` | ~12KB gzip | Server state: pagination, cache, optimistic deletes |
| `@radix-ui/react-alert-dialog` | ~4KB gzip | Delete confirmation: focus trap, a11y, portal |

---

## Visual Design

### Typography (Segoe UI / system-ui)

| Role | Size | Weight |
|------|------|--------|
| Page title | 1.25rem | 700 |
| Section heading | 0.875rem | 650, uppercase |
| Article title | 0.8125rem | 630 |
| Body text | 0.8125rem | 400 |
| Meta/small | 0.75rem | 400 |
| Badges/labels | 0.65rem | 550 |

### Source Type Badge Colors

| Type | Background (10% opacity) | Text | Dark mode text |
|------|-------------------------|------|----------------|
| PDF | rgba(220,38,38,0.1) | #dc2626 | #fca5a5 |
| HTML | rgba(22,163,74,0.1) | #16a34a | #6ee7b7 |
| URL | rgba(37,99,235,0.1) | #2563eb | #93c5fd |
| JSON | rgba(202,138,4,0.1) | #ca8a04 | #fcd34d |
| CSV | rgba(124,58,237,0.1) | #7c3aed | #c4b5fd |

### Transitions

All 0.15s ease. Respect `prefers-reduced-motion: reduce`.

### Dark Theme

Same `[data-theme='dark']` mechanism. Deep navy bg (#0b1220), not pure black.

---

## Key Interactions

### Row Expansion
- Click row → expand detail panel below (accordion, one at a time)
- 2px `var(--accent)` left border on expanded row
- Escape closes expansion
- Prefetch detail on 200ms hover via React Query `prefetchQuery`

### Delete Flow
1. Click Delete in expanded detail
2. Inline confirmation: "Delete 'Title' and its N parts? [Yes, delete] [Cancel]"
3. Optimistic removal from list
4. Undo toast (3-second window)
5. If Undo clicked → restore row, cancel delete
6. If timer expires → fire `DELETE /kb/articles/{article_id}`

### Import
- [+ Import] button scrolls to collapsible import section and expands it
- After success: 3-second message, auto-collapse, refetch article list
- New article highlighted briefly in list

### Search
- 300ms debounce on input
- React Query `keepPreviousData` for smooth transitions

---

## Accessibility

- All elements keyboard-navigable in DOM order
- Article rows: `aria-expanded` on expandable rows
- Delete confirmation: Radix AlertDialog handles focus trap + `role="alertdialog"`
- Toast: `role="status"` + `aria-live="polite"`
- Focus management: after delete → focus next row; after import → focus new article
- Color never sole indicator — badges always have text labels
- Minimum viewport: 1024px

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Empty KB | Full-page empty state with import CTAs |
| Hundreds of articles | Pagination (20/page) |
| Long titles | Truncate ~60 chars, full title on expand |
| Import in progress | Disable import buttons, show progress |
| Backend offline | Top banner with connection error |
| Delete last article | Transition to empty state |
| No timestamp (existing articles) | Show "Unknown" in Imported column |
| Section-less articles (PDF, URL) | Flat "N parts" instead of section grouping |

---

## MVP Scope

### Ships in v1
1. Single-column layout with stat cards
2. Article list with search + source type filter + pagination (20/page)
3. Expandable row detail (source, parts, preview, delete)
4. Per-article delete with undo toast
5. File import (collapsible section, reuses `/ingest/upload`)
6. URL import (collapsible section, reuses `/ingest/url`)
7. Health dashboard (article count, parts count, system status)
8. Dark/light theme
9. Empty state with import CTA
10. Skeleton table loader
11. Token auth gate (if `API_TOKEN` configured)

### Phase 2
- Bulk delete (multi-select + floating action bar)
- Manual article creation (`POST /kb/articles`)
- Semantic search (embedding-based)
- Column sorting
- Two-column layout upgrade (if needed)
- Keyboard shortcuts
- Import history / activity log

---

## Sidebar Simplification (Companion Change)

With the standalone KB management page, the sidebar should be decluttered:

### High Priority
1. **Replace KnowledgePanel** with status row + "Manage Knowledge Base" link (~688 lines removed: ImportTab, ManageTab, useKnowledgeImport, related CSS)
2. **Merge Compose + Draft panels** into single "Reply" panel (saves ~60-80px vertical space, removes 1 section heading)
3. **Deduplicate health polling** — BackendControl already fetches `/health` every 5s; KnowledgePanel's separate 10s poll is redundant. Pass doc counts via props or Zustand store.

### Medium Priority
4. **Collapse Status panel by default** when all services healthy (saves ~80px)
5. **Move model selector** to compact inline display: "Model: qwen2.5:14b [change]"
6. **Reorder panels**: Ticket context first (primary), Status below (secondary)
7. **Remove empty reply placeholder** — don't render reply box until reply exists

### Low Priority
8. Make Insert button `primary-btn` (blue) instead of `secondary-btn`
9. Generate/Cancel button merge — one button that toggles during generation
10. Inline disable reason on Generate button: "Backend offline" / "Open a ticket page first"

**Net effect:** 5 panels → 3, ~150-200px vertical space recovered, ~688 lines removed.
