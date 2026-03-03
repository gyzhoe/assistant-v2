# Sprint 6: Polish & Remaining Findings

**Goal:** Fix all remaining low/medium findings from the production reviews (performance, security, UX) to complete the hardening pass before feature work begins.

**Scope:** Fixes and polish only — no new features. All 15 items are low or medium severity.

---

## Quality Bar

This is an enterprise tool deployed to a shared helpdesk team handling sensitive data. Every line of code must be production-grade.

### Performance
- **No unnecessary work.** Don't poll when nothing is listening. Don't fetch when the result is cached. Don't re-render when props haven't changed.
- **Async by default.** Never block the event loop (backend) or the main thread (frontend). Use `asyncio.gather` for independent I/O, `AbortController` for cancellable requests.
- **Measure what you change.** If you optimize polling or caching, verify the improvement — don't just assume it's faster.

### Security
- **Validate all inputs.** Path params get regex constraints. Config values get type checks. User-facing strings get sanitized before logging.
- **Least privilege.** Don't expose more than needed — health endpoints return minimal info, cookies have the tightest flags possible, CSP is explicit.
- **No secrets in code, logs, or commits.** Hash or omit PII in logs. Never hardcode tokens. Follow OWASP top 10.
- **Audit trail.** Security-sensitive actions (login, delete, shutdown) must be logged with timestamp, client IP, and outcome.

### Code Quality
- **TypeScript strict, Python mypy strict.** No `any`, no `# type: ignore`, no shortcuts.
- **Tests for every change.** Not just happy path — test edge cases, error states, and the interaction between old and new code.
- **No dead code, no commented-out code, no TODOs.** Ship clean or don't ship.
- **Match existing patterns.** Read the surrounding code before writing. If there's an established pattern (singleton services, Zustand selectors, Radix primitives), use it — don't invent a new one.

---

## UX Guidelines

These items are polish — they're the details users notice. Every change must feel intentional, not bolted-on.

- **Match existing patterns.** The codebase already has Fluent Design tokens, Radix primitives, toast notifications, skeleton loaders, and `aria-*` attributes everywhere. New UI must use the same components and CSS variables — never invent new patterns.
- **Every interactive element needs all states:** default, hover, focus-visible, active, disabled, loading, success, error. Check dark mode too.
- **Transitions matter.** Use the existing `120ms` transition standard from `sidebar.css`. Collapsing/expanding panels, showing/hiding spinners, and confirm dialogs should all animate.
- **Respect the design system.** Accent blue `#0078d4`, neutral grays from `--surface`/`--border`/`--muted` tokens. No hardcoded colors. No new CSS variables unless absolutely necessary.
- **Accessibility is not optional.** Every new interactive element needs `aria-label` or visible label, keyboard operability, and focus management. Modals must trap focus. Confirm dialogs must auto-focus the safe action (Cancel, not Delete).
- **Test in the sidebar's narrow viewport.** The sidebar is ~360px wide. Tooltips, modals, and spinners must fit without overflow or awkward wrapping.
- **Copy should be concise and helpful.** Error messages explain what went wrong AND what to do. Confirmations state the consequence ("This will delete all 47 articles in this collection"). No jargon.
- **Don't surprise users.** If behavior changes (e.g., settings gear now opens a new tab), make it obvious. Use standard affordances — link icons for navigation, trash icons for delete, spinners for loading.

---

## Track A: Backend Polish (Small — Solo Lead)

**Branch:** `fix/backend-polish`

| # | Finding | Source | Severity | Files | Description |
|---|---------|--------|----------|-------|-------------|
| A1 | M2 | Security | MEDIUM | `routers/auth.py`, `config.py` | **Configurable cookie `secure` flag.** Add `SESSION_COOKIE_SECURE` config setting (default `False`). Set `secure=True` on `whd_session` cookie when config is enabled. Allows TLS deployments to get secure cookies without code change. |
| A2 | L1 | Security | LOW | `routers/generate.py:32` | **Sanitize ticket subject in logs.** Replace `body.ticket_subject[:80]` with a hash or generic label. Prevent PII from leaking into log files. |
| A3 | I8 | Performance | LOW | `services/rag_service.py:58` | **Speculative third RAG query.** Run the unfiltered KB fallback query in the initial `asyncio.gather` alongside the filtered query. Discard if not needed. Saves one round-trip when fallback triggers. |
| A4 | L6 | Security | LOW | `.github/workflows/release.yml:136` | **Hash-pinned pip downloads.** Generate `requirements.txt` with `--generate-hashes` and use `--require-hashes` in the release workflow `pip download` step. |
| A5 | L8 | Security | LOW | New `app/services/audit.py` | **Audit logger for admin actions.** Structured JSON audit log for: login, logout, session sweep, article delete, collection clear, shutdown. Separate log file with rotation. Keep it lightweight — just a logger, not a framework. |

**Tests:** Update affected test files. Expect ~5-10 test additions/modifications.

---

## Track B: Frontend Polish (Medium — Lead + Junior)

**Branch:** `fix/frontend-polish`

| # | Finding | Source | Severity | Files | Description |
|---|---------|--------|----------|-------|-------------|
| B1 | C4 | UX | MEDIUM | `sidebar/components/ManageTab.tsx` | **Modal confirm for Clear collection.** Replace inline "Sure? Yes/No" with Radix `ConfirmDialog` (already used in Management SPA). Destructive action that deletes ALL documents deserves a proper modal. |
| B2 | I4 | Performance | LOW-MED | `content/sidebar-host.ts` | **Narrow MutationObserver target.** When `#ticketDetailForm` not found, try more specific ancestors (main content area) before falling back to `document.body`. Add `attributeFilter` to ignore irrelevant mutations. |
| B3 | B6 | Performance | LOW | `sidebar/components/BackendControl.tsx` | **Pause health polling when hidden.** Add `visibilitychange` listener — pause polling when sidebar is not visible, resume immediately on focus. Standard browser optimization. |
| B4 | B7 | Performance | LOW | `sidebar/components/KnowledgePanel.tsx` | **Lazy polling when collapsed.** Don't start/continue the doc-count poll when the panel is collapsed. Resume when expanded. |
| B5 | I6 | Performance | LOW | `lib/storage.ts` | **Fix saveSettings race.** Write the full merged settings from the Zustand store directly instead of read-then-merge-then-write. Eliminates the two-async-op race window. |
| B6 | P3 | UX | LOW | `sidebar/components/ModelSelector.tsx` | **Model name tooltips.** Add a tooltip or subtitle showing model size/speed hint (e.g., "14B params, slower but smarter"). Map known model names to friendly descriptions. |
| B7 | P5 | UX | LOW | `sidebar/components/ImportTab.tsx` | **URL import spinner.** Add a spinner or indeterminate progress indicator for URL imports (can take 10+ seconds). Currently only shows "Importing..." text on disabled button. |
| B8 | P8 | UX | LOW | `management/components/Header.tsx` | **Settings gear links to options.** Replace the toast ("Right-click the extension icon...") with a direct link to the options page URL, or remove the gear icon entirely. |
| B9 | P9 | UX | LOW | `sidebar/components/BackendControl.tsx`, `options/OptionsPage.tsx` | **Onboarding reset.** Add a "Show Getting Started guide" link in Options page that clears the `onboarded` flag from `chrome.storage.local`. |
| B10 | L4 | Security | LOW | `public/manifest.json` | **Explicit CSP in manifest.** Add `content_security_policy.extension_pages: "script-src 'self'; object-src 'self'"` to document the security boundary (MV3 default is already secure). |

**Lead tasks:** B1, B2, B3, B4, B5
**Junior tasks:** B6, B7, B8, B9, B10

**Tests:** Expect ~5-8 new/modified tests.

---

## Track C: Docs (Small — Haiku solo)

**Branch:** `docs/sprint-6-changelog`

- Update `CHANGELOG.md` with all Sprint 6 changes
- Merge LAST (after A + B)

---

## Merge Order

1. **Track A** (backend) — no dependencies on other tracks
2. **Track B** (frontend) — no dependency on A (independent files)
3. **Track C** (docs) — merges LAST after A + B

Tracks A and B can run in parallel. No file overlap between them.

---

## Team Structure

| Role | Agent | Model | Track |
|------|-------|-------|-------|
| Backend Lead | TBD | Opus | Track A |
| Frontend Lead | TBD | Opus | Track B |
| Frontend Junior | TBD | Sonnet | Track B |
| Docs | TBD | Haiku | Track C |

---

## Verification

Each track must pass before merge:
- Backend: `ruff check .` + `mypy app/ ingestion/` + `pytest tests/ -v`
- Extension: `typecheck` + `lint` + `vitest run`
- No regressions in existing test counts (~347 backend, ~174 extension)
