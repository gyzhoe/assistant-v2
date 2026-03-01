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
