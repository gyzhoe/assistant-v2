# Feature Backlog & Future Ideas

Consolidated from the production review (2026-03-02) by Viktor, Beatrice, Ophelia, and Timmy.

---

## Tier 1: High Value, Achievable Now

These build on existing infrastructure. Each is a single sprint or less.

### Streaming LLM Replies (SSE)
**Value:** Reduces perceived generation latency from 10-30s to <1s.
**Status:** Half-built — `GenerateRequest` already has `stream` field, `AbortController` wired, Ollama supports streaming natively.
**Approach:** Backend `StreamingResponse` + SSE → frontend `ReadableStream` + `TextDecoder` → incremental Zustand store updates.
**Effort:** 1 sprint (backend + frontend)
**Sources:** Viktor B2, Ophelia U5, Timmy #10

### Confidence Indicator on Replies
**Value:** Tells technicians when to trust vs. verify the AI output.
**Status:** FREE — backend already returns `context_docs` with similarity scores in `GenerateResponse`, frontend ignores them entirely.
**Approach:** Count docs with score >= 0.75. Display colored chip: green (3+ matches), yellow (1-2), red (0). One component, zero backend changes.
**Effort:** Quick win (1 PR)
**Sources:** Ophelia F1, Timmy #7

### Ticket Notes Extraction
**Value:** Game-changer for reply quality — AI knows the full conversation history.
**Status:** Plan drafted, DOM investigation needed. Notes section structure documented in `memory/whd-ticket-dom.md`.
**Approach:** Extend `DOMReader` with `readNotes()`, add `notes` to `TicketData`, include in generate prompt as `NOTES HISTORY` section.
**Effort:** 1 sprint
**Sources:** Ophelia F2, Timmy #9

### Feedback Analytics Dashboard
**Value:** Proves the system's value to management. Actionable KB improvement signals.
**Status:** Data already collected in `rated_replies` ChromaDB collection — completely invisible.
**Approach:** New `GET /feedback/stats` endpoint + `FeedbackStats.tsx` in management SPA with rating counts by category and trend over time.
**Effort:** 1 sprint
**Sources:** Ophelia F5, Timmy #13

---

## Tier 2: High Value, Moderate Effort

### Stack Overflow Live Search
**Value:** Real-world solutions that Microsoft docs lack — networking, AD, driver issues.
**API:** Stack Exchange `search/advanced` — 300 req/day free, 10k/day with key. CC BY-SA 4.0.
**Approach:** New `StackOverflowService` alongside `MicrosoftDocsService`, parallel `asyncio.gather` at generation time. Filter to sysadmin tags, score >= 5.
**Effort:** 1 sprint
**Sources:** Memory backlog, Timmy #8

### Quick Reply Templates / Canned Responses
**Value:** Standard replies for repetitive tickets (password resets, VPN setup) — one click instead of AI generation.
**Approach:** `chrome.storage.sync` for template persistence, new `TemplateManager.tsx` in sidebar, templates can optionally feed into prompt suffix.
**Effort:** 1 sprint
**Sources:** Ophelia F9, Timmy #12

### Word Count & Regenerate Button
**Value:** Quick UX wins — show word count (prompt enforces 60-120 words), add visible "Regenerate" button for getting a fresh take.
**Approach:** Two small additions to `ReplyPanel.tsx`.
**Effort:** Quick win (1 PR)
**Sources:** Timmy #3, #4

### Keyboard Shortcuts for Power Users
**Value:** 40+ tickets/day users need speed. Mouse is the enemy.
**Approach:** `Ctrl+Enter` = generate, `Ctrl+Shift+Enter` = generate & insert, `Escape` = cancel. Shortcut cheat sheet in empty reply placeholder.
**Effort:** Quick win (1 PR)
**Sources:** Ophelia U4, Timmy #6

---

## Tier 3: Ambitious Features

### AI-Powered Ticket Triage & Routing
**Value:** Eliminates the invisible bottleneck of misrouted tickets.
**Approach:** New `POST /analyze` endpoint, lightweight prompt with `format: "json"`, returns category/complexity/urgency/routing suggestion. Trigger on page load.
**Effort:** 2 sprints
**Sources:** Ophelia F10, Timmy #14

### Reply Quality Learning Loop
**Value:** System learns from technician edits, not just thumbs up/down.
**Approach:** Compare generated vs. final text at insert time. If significant diff, store corrected version as high-quality few-shot example. Weight edited examples highest in `_get_dynamic_examples()`.
**Effort:** 2 sprints
**Sources:** Timmy #15

### Similar Ticket Finder
**Value:** Shows how similar past tickets were resolved — instant institutional knowledge.
**Approach:** Search `whd_tickets` collection by current ticket embedding. Show top 3 matches with subject, resolution, and "Use this reply" button.
**Effort:** 1-2 sprints
**Sources:** Ophelia F6

### Scheduled KB Auto-Refresh
**Value:** Keeps KB fresh without manual intervention — critical for fast-changing Microsoft docs.
**Approach:** Backend scheduler (`asyncio.create_task` with periodic wakeup), JSON config for URL + interval, management SPA panel for "Scheduled Sources".
**Effort:** 2 sprints
**Sources:** Timmy #16

### KB Article Creation from Replies
**Value:** Close the loop — great replies become KB articles with one click.
**Approach:** "Save to KB" button after edit, pre-fills article with ticket context + reply, calls create article API.
**Effort:** 1 sprint
**Sources:** Ophelia F7

---

## Tier 4: Dream Features (Long-term)

### Anomaly Detection for Ticket Spikes
Detect 5+ similar tickets in an hour → "Possible Incident" alert. Background clustering job, sidebar alert, management SPA notification.
**Sources:** Timmy #18

### Multi-Tech Collaboration Mode
Real-time collaborative reply editing via WebSockets. Google Docs-style for helpdesk replies. Session identified by ticket URL.
**Sources:** Timmy #17

### Emotion-Aware Reply Tone
Detect frustrated/calm/technical/urgent tone in ticket description. Automatically adjust reply tone — more empathetic for stressed users, more technical for IT staff.
**Sources:** Timmy wild ideas

### Azure OpenAI as LLM Provider
Near drop-in replacement for Ollama. Config switch `LLM_PROVIDER=ollama|azure_openai`. GPT-4o-mini at ~$1/month vs $0 local.
**Sources:** Memory backlog

### Personal Reply Library
Technicians star their own best replies for future reference. `chrome.storage.local`, no backend changes. Browseable from sidebar with search.
**Sources:** Timmy wild ideas

---

## Security Enhancements (Post-Sprint 5)

These are hardening items beyond the Sprint 5 fixes:

| Item | Description | Priority |
|------|-------------|----------|
| Audit logging | Structured audit log for login, delete, clear, shutdown actions | Medium |
| Request signing | HMAC between extension and backend to prevent replay | Low |
| Token rotation | `POST /auth/rotate-token` endpoint + scheduled reminders | Low |
| Dependency hash pinning | `uv pip compile --generate-hashes` in release workflow | Low |
| CSP headers for /manage | `default-src 'self'; script-src 'self'` | Low |
| IP allowlisting | Optional `ALLOWED_CLIENT_IPS` config for network-exposed deployments | Low |
| TLS support | Optional HTTPS via uvicorn SSL args, flip `secure=True` on cookies | Low |
| RBAC | Role-based access if tool grows beyond single-role technicians | Low |

---

*Last updated: 2026-03-02*
*Sources: review-performance.md, review-security.md, review-ux.md, review-ideas.md*
