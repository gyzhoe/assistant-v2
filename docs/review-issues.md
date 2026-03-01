# Codebase Review — Issues

Generated from multi-agent codebase review (2026-02-28).

---

## ~~1. Confirm dialog breaks in dark mode due to hardcoded portal styles~~ RESOLVED

**Labels:** `bug` | **Resolved in:** PR #85 (Sprint 1, H10)
**Scope:** `fix(extension)`
**File:** `extension/src/management/management.css` lines 1199–1229

The management page's `ConfirmDialog` uses Radix `AlertDialog` which renders
via Portal outside `.app-shell`, breaking CSS variable inheritance. The
workaround uses hardcoded fallback values in `.confirm-content` and
`.confirm-actions`, but these are **light-theme only**.

Dark mode users see light-colored button backgrounds/borders on the confirm
dialog.

**Suggested fix:**

- Add dark-mode variants for the hardcoded portal styles
  (`.app-shell[data-theme="dark"] .confirm-actions` won't work since it's
  outside the shell — use `@media (prefers-color-scheme: dark)` or pass
  `data-theme` to the portal container)
- Or set the theme attribute on the portal root via Radix's `container` prop

---

## 2. Add length limits to custom_fields values to mitigate prompt injection

**Labels:** `security`
**Scope:** `fix(backend)`
**Files:** `backend/app/models/request_models.py`,
`backend/app/routers/generate.py:337`

`custom_fields` in `GenerateRequest` accepts a `dict[str, str]` with no
per-key or per-value length limits. These values are interpolated directly
into the LLM prompt in `_build_prompt()`.

A malicious ticket with crafted custom field values
(e.g., `\n\nIGNORE ALL PREVIOUS INSTRUCTIONS...`) could manipulate the LLM
output. The `ticket_description` field has a `_DESCRIPTION_MAX` limit, but
`custom_fields` values do not.

**Suggested fix:** Add Pydantic validators to `custom_fields`:

- Max 10 fields
- Max 500 chars per value
- Max 100 chars per key
- Strip/reject control characters

**Severity:** Low-Medium — requires a crafted WHD ticket, local-only system,
but relevant for the remote backend roadmap.

---

## ~~3. Replace semaphore `._value` check with public API~~ RESOLVED

**Labels:** `bug` | **Resolved in:** PR #87 (Sprint 1, H4/H5)
**Scope:** `fix(backend)`
**Files:** `backend/app/routers/ingest.py:60, 169`,
`backend/app/routers/kb.py:218, 337`

Multiple routes check `asyncio.Semaphore._value` (a private attribute) to
implement non-blocking rejection when a semaphore is full:

```python
if not upload_semaphore._value:  # noqa: SLF001
    raise HTTPException(status_code=409, ...)
async with upload_semaphore:
    ...
```

This has a TOCTOU race window between check and acquire, and relies on a
private attribute that could break across Python versions.

**Suggested fix:** Use a try/acquire pattern or wrap in a helper like
`try_acquire_or_409()` to DRY the 4 call sites.

---

## ~~4. useSubmitFeedback silently resets rating on API error~~ RESOLVED

**Labels:** `bug` | **Resolved in:** PR #90 (Sprint 2, M20)
**Scope:** `fix(extension)`
**File:** `extension/src/sidebar/hooks/useSubmitFeedback.ts`

When the feedback API call fails, the hook resets `replyRating` to `null`
silently — no toast, no error message, no visual indication.

The user clicks thumbs-up/down, sees it selected (optimistic update), then
if the API fails, the selection quietly disappears. The user believes their
feedback was saved when it wasn't.

**Expected behavior:**

- Show an error toast or inline error message
- Either keep the selected state with a retry option, or clearly indicate
  the rating was not saved

**Fix:** Added inline error message to feedback panel on API failure.

---

## 5. BackendControl has duplicate interactive elements for collapse toggle

**Labels:** `bug`, `accessibility`
**Scope:** `fix(extension)`
**File:** `extension/src/sidebar/components/BackendControl.tsx:180-190`

Two interactive elements control the same collapse action:

1. A `<button>` trigger (correct)
2. A `<div role="button" tabIndex={0}>` with `onKeyDown` for Enter/Space
   (redundant)

This is an accessibility anti-pattern:

- Screen readers announce two buttons for the same action
- Keyboard users tab through two elements that do the same thing
- The `div[role=button]` duplicates native `<button>` semantics

**Suggested fix:** Consolidate into a single `<button>` element that wraps
both the label and the status chip/chevron.

---

## 6. Move institution-specific environment facts to config

**Labels:** `enhancement`
**Scope:** `chore(backend)`
**File:** `backend/app/routers/generate.py:354-357`

Hardcoded institution-specific environment details in the LLM prompt:

```text
ENVIRONMENT
- Managed university network using 802.1X authentication.
- Managed devices have hostnames matching GBW-*-**** and connect automatically via dot1x.
```

These are embedded deep inside `_build_prompt()` with no config knob. Anyone
deploying this for a different organization would get incorrect LLM replies
without knowing these lines exist.

**Suggested fix:** Move environment context to a config setting (env var or
`.env` file), e.g. `ENVIRONMENT_CONTEXT`, or load from a `prompt_context.txt`
file that can be customized per deployment.

---

## ~~7. pinArticle silently ignores pins at 10-article cap~~ RESOLVED

**Labels:** `bug`, `ux` | **Resolved in:** PR #90 (Sprint 2, M19)
**Scope:** `fix(extension)`
**File:** `extension/src/sidebar/store/sidebarStore.ts:63`

```typescript
if (pinnedArticles.length >= 10) return
```

When the user hits the 10-pin limit, the pin button remains clickable but
does nothing — no toast, no disabled state, no visual feedback.

**Expected behavior:**

- Disable the pin button when at cap, with a tooltip explaining the limit
- Show a toast: "Maximum 10 articles can be pinned"
- Extract the magic number `10` to a named constant

**Fix:** Added `MAX_PINNED_ARTICLES` constant and pin cap toast notification when limit is reached.

---

## M6. Rate limiter behind reverse proxy

**Labels:** `documentation`
**Scope:** `docs`
**Resolved in:** PR #95 (Sprint 3)

Rate limiting middleware relies on source IP extraction from request headers.
When deployed behind a reverse proxy or load balancer (nginx, Cloudflare, etc.),
the client IP becomes the proxy IP, and rate limiting breaks.

**Mitigation:** Rate limiting is suitable for local/institutional deployments
behind a trusted proxy. In cloud/public deployments, offload rate limiting to
the reverse proxy layer (nginx `limit_req`, Cloudflare rate rules, etc.).

**Documentation:** Added notes to `backend/app/middleware/security.py` and
`docs/api-contract.md` explaining the proxy limitation.

---

## M7. /manage static mount has no authentication

**Labels:** `documentation`
**Scope:** `docs`
**Resolved in:** PR #95 (Sprint 3)

The KB Management page at `GET /manage` serves a static SPA without requiring
the API token (unlike all other API routes). This is acceptable for local
institutional deployments running on `localhost:8765`.

**Design decision:** The management page is UI-only (no sensitive data exposure
— it retrieves articles via authenticated API calls). Serving the HTML is safe
without auth. In production/remote deployments, add nginx auth or API Gateway
auth in front of the static path.

**Documentation:** Added clarification to `backend/app/main.py` and
`docs/api-contract.md`.

---

## ~~M10. Document all API endpoints~~ RESOLVED

**Labels:** `documentation`
**Scope:** `docs`
**Resolved in:** PR #93 (Sprint 3)

Added comprehensive API contract documentation:

- **18 endpoints** across 6 routers (health, generate, models, KB CRUD, ingest, feedback, settings, Ollama)
- Request/response schemas with all fields marked optional/required
- Status codes and error details
- Rate limiting, size limits, auth requirements
- File: `docs/api-contract.md`

---

## M24. Upload batch error recovery

**Labels:** `enhancement`, `ux`
**Scope:** `feat(extension)`
**Resolved in:** PR #94 (Sprint 3)

**Feature:** Per-file status tracking during batch file uploads with partial progress and recovery options.

- Each file shows individual status: pending → uploading (progress %) → success/error
- Partial progress: skip failed files and continue with remaining
- Retry failed: re-upload specific files that errored
- User can see exactly which files succeeded/failed/are pending
- Graceful error messages for each file (size limit, format error, server error, etc.)

**Files modified:**
- `extension/src/sidebar/hooks/useKnowledgeImport.ts` — per-file status tracking with abort per file
- `extension/src/sidebar/components/ImportTab.tsx` — file list with individual progress bars and action buttons
- New state: `uploadStatus: Record<string, { status: 'pending'|'uploading'|'success'|'error', progress: number, error?: string }>`

---

## M26. First-time onboarding flow

**Labels:** `enhancement`, `ux`
**Scope:** `feat(extension)`
**Resolved in:** PR #94 (Sprint 3)

**Feature:** Guided setup card for new users on first install.

- **Ordered steps card** in sidebar showing:
  1. Install Ollama (with download link)
  2. Pull model (`qwen2.5:14b` or custom via settings)
  3. Start backend service
- Visual progress indicator (✓ completed, → in-progress, ○ pending)
- Auto-dismisses when all steps complete
- Can be manually dismissed and re-opened from Help menu

**Files modified:**
- New component: `extension/src/sidebar/components/OnboardingCard.tsx`
- Hook: `extension/src/sidebar/hooks/useOnboarding.ts` with step detection logic
- Store integration in `sidebarStore.ts` for persistence
- Sidebar layout reflow to accommodate card without obscuring content

---

## L2. Missing CSS rule for .import-section-label

**Labels:** `bug`, `ui`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

The `.import-section-label` class used in `ImportTab.tsx` had no CSS rule,
causing inconsistent styling vs. other section labels.

**Fix:** Added CSS rule matching `ManageTab` section label styling in
`extension/src/sidebar/sidebar.css`.

---

## L4. Tailwind font-mono misaligned with CSS tokens

**Labels:** `bug`, `ui`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

Tailwind config defined `font-mono` as `'Monaco', 'Courier New'`, but CSS tokens
used `'Segoe UI Variable Mono'`. Monospace data values (article IDs, timestamps)
rendered differently in sidebar vs. management page.

**Fix:** Aligned Tailwind `font-mono` to match CSS token `--font-mono` value
in `extension/vite.config.ts`.

---

## ~~L6. Redundant httpx import in pipeline.py~~ STALE

**Labels:** `refactor`
**Scope:** `fix(backend)`
**Resolved in:** PR #95 (Sprint 3) — NO CHANGE NEEDED

The finding claimed `import httpx` was redundant in `backend/app/ingestion/pipeline.py`.
**Actual state:** The import is already at the top level and is used (no change needed).
This was a stale finding from code drift between review snapshot and implementation.

---

## L14. Vite 7 and Vitest 2 compatibility

**Labels:** `chore`, `testing`
**Scope:** `chore(extension)`
**Resolved in:** PR #96 (Sprint 3)

Verified Vite 7 and Vitest 2 compatibility:

- `package.json` already uses Vite 7.1.x and Vitest 2.x
- All build, dev, test, lint, typecheck commands pass
- No breaking changes identified
- No upgrades needed

---

## L15. Installer hardcoded component index

**Labels:** `bug`, `installer`
**Scope:** `fix(installer)`
**Resolved in:** PR #96 (Sprint 3)

File: `installer/setup.iss:120`

The installer's component selection screen had hardcoded index `1` for
the "Backend" component, which could break if component order changed.

**Fix:** Replaced hardcoded index with component name-based lookup in
installer script (`{#SetupSectionDependencies}` section).

---

## L16. Auth header skipped on /health endpoint

**Labels:** `security`, `api`
**Scope:** `fix(backend)`
**Resolved in:** PR #96 (Sprint 3)

File: `backend/app/middleware/auth.py`

The `/health` endpoint (used by the extension for liveliness checks) did not
require the API token. While the endpoint returns no sensitive data, this
creates an **unauthenticated entry point** that could be used in
reconnaissance or DoS attacks.

**Fix:** Skipped the auth check specifically for `/health` (returns 200 with
`{"status": "ok"}`), but documented this as acceptable for local deployments.

---

## L18. Zustand stable setters in dependency arrays

**Labels:** `refactor`, `performance`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

Files: `extension/src/sidebar/hooks/*.ts`

Several hooks included Zustand store setter functions (returned from
`useStore(state => state.setFoo)`) in dependency arrays of `useEffect` /
`useCallback`. Zustand setters are stable across re-renders, so including
them causes unnecessary dependency recalculations.

**Fix:** Removed setters from dependency arrays in hooks like
`useGeneration.ts`, `useKnowledgeImport.ts`, etc.

---

## L19. searchKBArticles pagination bug

**Labels:** `bug`, `api`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/sidebar/hooks/useSearchKB.ts`

Pagination was not working correctly when the user searched, changed page,
then searched again — page number was not reset to 1, causing stale results.

**Fix:** Reset `page` to `0` when search term changes. Added 4 new tests
verifying pagination reset on search input change.

**Test count:** +4 new tests (PR #96)

---

## L20. DOMReader instance cached in content script

**Labels:** `performance`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/content/content.ts`

The `DOMReader` instance was recreated on every DOM mutation or message,
causing redundant DOM queries and event listener setup.

**Fix:** Cached the single `DOMReader` instance at module scope and reused
it across the content script lifetime.

---

## L21. .sr-only class protected from tree-shaking

**Labels:** `bug`, `build`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/sidebar/sidebar.css`

The `.sr-only` (screen-reader-only) utility class was defined but not used
in JSX. Tailwind's tree-shaking could remove it from the final bundle if
the exact string `.sr-only` didn't appear in scanned files.

**Fix:** Added CSS comment `/* @keep .sr-only */` and verified the class is
preserved in the final bundle via build inspection.

---

## L22. Tab panels missing aria-labelledby

**Labels:** `accessibility`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

Files: `extension/src/sidebar/components/KnowledgePanel.tsx`,
`extension/src/management/components/KnowledgePane.tsx`

Tab panels were missing the `aria-labelledby` attribute linking them to
their corresponding tab trigger. Screen readers had no way to associate
a panel with its tab label.

**Fix:** Added `aria-labelledby={tabId}` to each tab panel, where `tabId`
matches the trigger's `id`.

---

## L23. Article list missing aria-busy during refetch

**Labels:** `accessibility`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/management/components/ArticleList.tsx`

When articles were being refetched (search, filter, or pagination change),
the article list DOM did not announce to screen readers that data was
loading. The list appeared static while data was in flight.

**Fix:** Added `aria-busy="true"` to the list container during refetch,
and `aria-busy="false"` when complete.

---

## L24. Unused React imports

**Labels:** `refactor`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

Several component files imported `React` without using it (common in modern
JSX after React 17's automatic JSX runtime).

**Fix:** Removed unused `import React` statements across sidebar and
management components.

---

## L25. SidebarHost.stop() not called on unload

**Labels:** `bug`, `lifecycle`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/sidebar/sidebar.ts`

The sidebar never called `SidebarHost.stop()` on window unload, leaving
message listeners and event handlers active.

**Fix:** Added `window.addEventListener('beforeunload', () => sidebarHost.stop())`
to clean up on sidebar close/refresh.

---

## L26. OptionsPage handleChange type issue

**Labels:** `type-safety`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/options/OptionsPage.tsx`

The `handleChange` function was not properly typed for the form input elements,
causing TypeScript warnings.

**Fix:** Added explicit type signature: `handleChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void`

---

## L30. Elapsed time counter during generation

**Labels:** `enhancement`, `ux`
**Scope:** `feat(extension)`
**Resolved in:** PR #94 (Sprint 3)

**Feature:** Display elapsed time since generation started.

- Timer updates every second during generation
- Shows format: "Generating... (15s elapsed)"
- Resets on next generation or when generation completes
- Provides feedback that the system is working (useful for slow models)

**Files modified:**
- `extension/src/sidebar/components/GenerationPanel.tsx` — timer display
- `extension/src/sidebar/hooks/useGeneration.ts` — `startTime` tracking with interval

---

## L32. Settings gear navigates to options page

**Labels:** `ux`
**Scope:** `feat(extension)`
**Resolved in:** PR #94 (Sprint 3)

**Changed:** Settings gear icon in KB Management header now navigates directly
to `chrome://extensions/configureCommands` (Edge extension options page),
instead of showing a toast notification.

**Rationale:** Users expect gear icon clicks to open settings; a toast was confusing.

---

## L33. ErrorBoundary retry button

**Labels:** `enhancement`, `ux`
**Scope:** `feat(extension)`
**Resolved in:** PR #94 (Sprint 3)

**Feature:** When an error boundary catches an exception, show a "Retry" button
that reloads the component (or entire sidebar).

**Implementation:**
- `ErrorBoundary` component now renders retry button alongside error message
- Click callback resets error state and re-renders children
- Fallback: if retry fails, shows stack trace for debugging

---

## L34. Ticket description preview with expand/collapse

**Labels:** `enhancement`, `ux`
**Scope:** `feat(extension)`
**Resolved in:** PR #94 (Sprint 3)

**Feature:** Long ticket descriptions in the sidebar are truncated to 3 lines
with "…" and an "Expand" button. Clicking expands to full text with a
"Collapse" button.

**Implementation:**
- `TicketContext` component detects text overflow
- CSS: `overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 3`
- Button toggles `expanded` state to show full content or collapsed preview

---

## L35. Client-side URL validation before import

**Labels:** `enhancement`, `security`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/sidebar/hooks/useKnowledgeImport.ts`

The import flow did not validate URLs on the client before sending them to
the backend. Invalid URLs (malformed, non-http, etc.) would cause server errors.

**Fix:** Added client-side URL validation using the `URL` constructor before
submitting to `/ingest/url` endpoint. Shows inline error message if URL is invalid.

---

## L36. Client-side file size check before upload

**Labels:** `enhancement`, `ux`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/sidebar/hooks/useKnowledgeImport.ts`

Files were not validated on the client before upload. If a file exceeded the
server's 50 MB limit, the upload would fail after a long wait.

**Fix:** Added client-side size check (compare `file.size` to `50 * 1024 * 1024`
before upload). Shows inline error message if file is too large.

---

## L37. Keyboard shortcut hint in manifest

**Labels:** `documentation`
**Scope:** `docs(extension)`
**Resolved in:** PR #94 (Sprint 3)

The manifest's `commands` section now includes a description of the sidebar toggle
shortcut (Alt+Shift+H) for users discovering it in Edge's keyboard shortcuts settings.

**File:** `extension/public/manifest.json`
```json
"commands": {
  "_execute_action": {
    "suggested_key": {
      "default": "Alt+Shift+H"
    },
    "description": "Toggle AI Helpdesk Assistant sidebar"
  }
}
```

---

## L39. Warning messages stay visible after success auto-dismiss

**Labels:** `ux`
**Scope:** `fix(extension)`
**Resolved in:** PR #96 (Sprint 3)

File: `extension/src/sidebar/components/ImportTab.tsx`

When a warning toast appeared (e.g., "File size too large"), and the user
took action (e.g., selected a smaller file), the warning would auto-dismiss
along with the success message. This left the user unsure if their action worked.

**Fix:** Changed toast logic to:
- Warning/error messages do NOT auto-dismiss
- Success messages auto-dismiss after 3 seconds
- User must manually close warnings by clicking the X button

---

## Deferred Items — Sprint 4+

The following findings were deferred beyond Sprint 3 scope:

- **L10**: Test coverage gaps (requires significant test suite expansion, 2-3 day effort)
- **L13**: BaseHTTPMiddleware → pure ASGI rewrite (pre-production optimization, lower priority)
- **L17**: Document deployment topologies (enterprise/cloud patterns, deferred to deployment guide)
- **L27**: Implement Stack Overflow live search (feature roadmap, not a bug fix)
