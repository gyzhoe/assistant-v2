# UX Review

## Executive Summary

The AI Helpdesk Assistant delivers a polished, well-structured frontend with strong fundamentals: consistent Fluent Design theming, comprehensive ARIA markup, proper loading/error/empty states, and a clean information hierarchy. The codebase reflects multiple rounds of deliberate UX improvements. The main areas for production hardening are around reply workflow efficiency (too many clicks to go from "Generate" to "Inserted"), missing keyboard shortcuts for power users, and a few interaction patterns that would benefit from progressive disclosure and animation refinement.

## Critical UX Issues

### C1. Reply workflow requires too many steps
**Files:** `extension/src/sidebar/components/ReplyPanel.tsx:62-87`, `InsertButton.tsx`
**Scenario:** Technician opens a ticket, generates a reply, reviews it, then clicks "Insert reply". That is 3 distinct actions (Generate -> review -> Insert) with no shortcut to skip the review step.
**Impact:** For experienced users who trust the AI output, there is no "Generate & Insert" one-click option. On a busy day handling 50+ tickets, this adds significant friction.

### C2. No copy-to-clipboard button for the generated reply
**Files:** `extension/src/sidebar/components/ReplyPanel.tsx:103-164`
**Scenario:** If the Insert button fails (textarea not found), or the user wants to paste the reply into a different field (email, Teams, another system), they must manually select all text in the reply box and copy it. There is no copy button.
**Impact:** The Insert mechanism depends on finding `textarea#techNotes` in the DOM. If WHD changes its DOM structure or the user wants to use the reply elsewhere, they have no easy fallback.

### C3. Generated reply is lost on page navigation
**Files:** `extension/src/sidebar/store/sidebarStore.ts` (Zustand store, no persistence)
**Scenario:** A technician generates a reply, navigates to another ticket to check something, then comes back. The reply, rating, and all state are gone because the Zustand store resets and there is no persistence layer.
**Impact:** Lost work is one of the most frustrating UX problems. Technicians working on complex tickets may need to cross-reference other tickets.

### C4. No confirmation before destructive "Clear" action in sidebar ManageTab
**Files:** `extension/src/sidebar/components/ManageTab.tsx:88-116`
**Scenario:** The inline "Sure? Yes / No" confirmation for clearing a collection is easy to mis-click. The "No" button auto-focuses (good), but the confirmation is a small inline text, not a modal dialog. For an action that deletes ALL documents in a collection, this is insufficient.
**Impact:** Accidental deletion of entire ticket or KB collections with no undo path.

### C5. DOMInserter has only 3 hardcoded selectors
**Files:** `extension/src/content/dom-inserter.ts:2-6`
**Scenario:** The insert target is limited to `textarea#techNotes`, `textarea[name="techNote"]`, and `#techNotesDiv textarea`. If WHD is configured differently, or the user wants to insert into a different field (e.g., a public reply field vs tech notes), the insert silently fails.
**Impact:** Users get "Insert failed" with no guidance on what went wrong or how to fix it. The Options page allows overriding DOM *reader* selectors but not the *inserter* target.

## Polish Opportunities

### P1. Skeleton loader does not match actual reply shape
**Files:** `extension/src/sidebar/components/SkeletonLoader.tsx`
The skeleton shows fixed-width bars (100%, 80%, 75%, 85%) which is a reasonable approximation, but the reply output is a single continuous text block. The skeleton creates an expectation of structured content (like a card with multiple fields) rather than prose. A single pulsing text area placeholder would better match the actual output.

### P2. Reply text display is plain text only - no markdown rendering
**Files:** `extension/src/sidebar/components/ReplyPanel.tsx:157-160`
The generated reply is rendered inside a `<div>` with `white-space: pre-wrap`. The LLM may produce markdown (lists, bold, headers) which displays as raw text. Even basic markdown rendering (bold, lists, links) would make replies more readable during review.

### P3. Model selector dropdown shows raw model identifiers
**Files:** `extension/src/sidebar/components/ModelSelector.tsx:55-58`
Model names like `qwen2.5:14b` are displayed as-is. Users unfamiliar with Ollama model naming conventions get no help understanding what these mean. A tooltip or subtitle indicating model size/speed tradeoff would help.

### P4. Settings button in sidebar header looks like a second theme toggle
**Files:** `extension/src/sidebar/components/BackendControl.tsx:305-316`
The settings gear icon uses the same `theme-toggle` CSS class as the theme button, making them visually identical. Users must hover to see the tooltip distinction. The gear icon should be visually differentiated (different border style or no border).

### P5. URL import has no loading state animation
**Files:** `extension/src/sidebar/components/ImportTab.tsx:266-273`
The "Importing..." text on the button is the only loading indicator for URL imports. Unlike file uploads which get a progress bar, URL imports (which can take 10+ seconds for large pages) only show a disabled button with changed text. A spinner or indeterminate progress bar would set better expectations.

### P6. Success messages auto-dismiss too quickly
**Files:** `extension/src/sidebar/components/ManageTab.tsx:16` (3000ms), `ImportTab.tsx:10` (4000ms), `InsertButton.tsx:22` (2000ms)
Auto-dismiss timers range from 2-4 seconds. For users who are multitasking or looking at the WHD page when a sidebar action completes, they may miss the confirmation entirely. The "Inserted" confirmation at 2 seconds is especially brief.

### P7. Article editor lacks markdown preview
**Files:** `extension/src/management/components/ArticleEditor.tsx:337-345`
The article content textarea accepts markdown and even hints about `##` headings, but there is no preview mode. Users cannot see how their markdown will render or how it will be chunked.

### P8. Management SPA settings button shows a toast instead of navigating
**Files:** `extension/src/management/components/Header.tsx:70-79`
Clicking the gear icon shows a toast saying "Right-click the extension icon..." which is unintuitive. The settings gear affordance universally means "open settings", not "show instructions about how to find settings elsewhere". Either link directly to the options page URL or remove the gear icon.

### P9. Onboarding card dismissal is permanent
**Files:** `extension/src/sidebar/components/BackendControl.tsx:172-175`
Once dismissed, the onboarding card is permanently hidden via `chrome.storage.local`. If a user dismissed it prematurely and later needs the setup steps again, there is no way to re-show it. A "Getting Started" link in the Options page or a reset button would help.

### P10. No toast/notification system in the sidebar
Unlike the Management SPA which has a full toast system (`Toast.tsx`), the sidebar uses inline text for all feedback. This means success/error messages are scattered across different components with inconsistent styling and behavior. A unified notification approach would improve consistency.

## Accessibility Audit

### Good Practices (already implemented)
- `role="alert"` and `aria-live="assertive"` on error states (`ErrorState.tsx:12-13`)
- `aria-live="polite"` on skeleton loader (`SkeletonLoader.tsx:16`) and insert feedback (`InsertButton.tsx:74`)
- `aria-expanded` on all collapsible sections
- `aria-controls` linking triggers to panels
- `aria-selected` on Knowledge Base tab strip (`KnowledgePanel.tsx:85-86`)
- `aria-label` on search inputs, buttons, and interactive elements
- `aria-busy` on loading states
- `aria-pressed` on rating toggle buttons (`ReplyPanel.tsx:114,120`)
- `role="list"` and `role="listitem"` on KB search results and pinned articles
- `sr-only` class for screen reader announcements (`InsertButton.tsx:74`)
- `@media (prefers-reduced-motion: reduce)` disables animations (`sidebar.css:927-931,1044-1048`)

### A1. Missing `aria-label` on sidebar main sections
**Files:** `extension/src/sidebar/App.tsx:19`
The `<main>` element has `role="main"` but no `aria-label`. With multiple panels, screen reader users benefit from a labeled landmark (e.g., `aria-label="AI Helpdesk sidebar"`).

### A2. Tab strip missing `aria-orientation`
**Files:** `extension/src/sidebar/components/KnowledgePanel.tsx:81`
The KB tab strip has `role="tablist"` but does not specify `aria-orientation="horizontal"`, which is the default but explicit is better for assistive tech. More importantly, the tab panels lack `role="tabpanel"` IDs that match `aria-controls` on inactive tabs. Only the active panel is rendered, which means the `aria-controls` on the inactive tab points to a non-existent element.

### A3. Insufficient color contrast for muted text
**Files:** `sidebar.css:29` (light: `#636c76` on `#f6f8fa`), `sidebar.css:69` (dark: `#8b949e` on `#0d1117`)
The `--muted` color is used extensively for secondary text, hints, and labels. Light mode: `#636c76` on `#f6f8fa` yields approximately 4.2:1 contrast ratio, which barely passes WCAG AA for normal text but fails for small text (<14px). Many muted text elements use `font-size: 0.6875rem` (11px), which falls below the AA threshold. Dark mode is similar.

### A4. Rating buttons use emoji without text alternative
**Files:** `extension/src/sidebar/components/ReplyPanel.tsx:116-126`
The thumbs up/down buttons use HTML entities (`&#x1F44D;` / `&#x1F44E;`) with `aria-label`, which is correct. However, the emoji rendering varies across platforms and may not be visible to users with certain font configurations. Consider adding a tooltip or visible text label as well.

### A5. Drop zone has `role="button"` but no accessible name for keyboard users
**Files:** `extension/src/sidebar/components/ImportTab.tsx:237-247`
The drop zone has `role="button"` and `tabIndex={0}` with `aria-label`, which is good. However, when focused via keyboard, there is no visible focus indicator distinct from the hover state. The `kb-drop-zone:focus-visible` style (`sidebar.css:1142-1145`) uses `box-shadow` which is adequate.

### A6. Confirm dialog in Management SPA traps focus correctly (Radix)
**Files:** `extension/src/management/components/ConfirmDialog.tsx`
Good: Uses Radix AlertDialog which handles focus trapping, escape-to-close, and return-focus-on-close automatically. No issues here.

### A7. No skip navigation link
Neither the sidebar nor the management SPA provides a "Skip to main content" link. For the sidebar this is less critical (it IS the main content), but the management SPA has a sticky header that keyboard users must tab through on every page load.

## What's Done Well

### Onboarding flow is excellent
**Files:** `extension/src/sidebar/components/BackendControl.tsx:20-85`
The step-by-step onboarding card that appears when services are down is a standout feature. It auto-detects service readiness (Ollama, model, backend) and auto-dismisses when all checks pass. This turns a potentially confusing first-run experience into a guided setup.

### Error handling is thorough and user-friendly
**Files:** `extension/src/sidebar/hooks/useGenerateReply.ts:49-66`
Error messages are contextual and actionable: "Ollama is not running. Please start it and try again" instead of generic "Error 503". The `ErrorState` component consistently offers a retry button. The `ErrorBoundary` includes both retry and copy-error-details actions.

### Optimistic updates with undo in Management SPA
**Files:** `extension/src/management/components/ArticleList.tsx:60-91`
Article deletion uses optimistic removal from the list with an 8-second undo window via toast notification. The actual DELETE call is delayed, giving users a genuine undo path. This is a best-practice pattern rarely seen in internal tools.

### File upload batch processing with partial failure recovery
**Files:** `extension/src/sidebar/hooks/useKnowledgeImport.ts`, `extension/src/sidebar/components/ImportTab.tsx`
The import flow handles success, partial success, and failure states independently per file. Users can retry only failed files. The cancel button properly aborts in-flight requests and resets uploading files to pending. This is production-grade batch upload UX.

### Design system consistency
Both the sidebar and management SPA share a cohesive token-based design system with proper light/dark theme support. CSS custom properties are well-organized with clear naming (`--accent`, `--ok-text`, `--error`, etc.). The Fluent Design language is consistently applied.

### Readiness badge grid
**Files:** `extension/src/sidebar/components/BackendControl.tsx:265-283`
The four-item readiness checklist (Ticket detected, Backend connected, Ollama ready, Model selected) gives users instant visibility into system state. The status chip in the collapsed header provides at-a-glance status without expanding.

### Debounced search with abort controller
**Files:** `extension/src/sidebar/components/KBContextPicker.tsx:22-63`
KB article search properly debounces at 300ms, cancels in-flight requests on new input, and handles race conditions via abort controller. This prevents stale results from overwriting fresh ones.

### Prefetch on hover in Management SPA
**Files:** `extension/src/management/components/ArticleList.tsx:106-112`
Article detail data is prefetched when the user hovers over a row, making expand-on-click feel instant. Combined with React Query's stale time, this is a subtle but effective performance optimization.

## Brainstorm: UX Improvements

### U1. One-click "Generate & Insert" button
Add a secondary action to the Generate button that combines generation and automatic insertion. When the user has already used the tool and trusts the output quality, this eliminates the review step. Implementation: a split button or a "Quick Insert" toggle in settings that auto-inserts after generation completes.

### U2. Copy button on generated reply
Add a clipboard copy button next to the Edit/Preview toggle in the draft header. Show a brief "Copied" confirmation. This provides a universal fallback when Insert fails or the user wants to use the reply in another application.

### U3. Reply history / session persistence
Persist the last N generated replies in `chrome.storage.session` (session-scoped, not synced). When the user navigates back to a ticket, restore the last reply generated for that ticket URL. Implementation: key by `ticketUrl` in the Zustand store, persist via `zustand/middleware/persist` with a custom `chrome.storage.session` adapter.

### U4. Keyboard shortcuts for power users
- `Ctrl+Enter` to generate (when sidebar is focused)
- `Ctrl+Shift+Enter` to generate and insert
- `Ctrl+C` on the reply box to copy (when reply is focused)
- `Escape` to cancel generation
Display a keyboard shortcut cheat sheet in the empty reply placeholder.

### U5. Streaming reply generation
Replace the skeleton loader with a streaming text display that shows the reply being generated token-by-token. The backend already supports `stream: false` as an option, implying streaming is architecturally possible. This would dramatically reduce perceived latency (users can start reading before generation completes).

### U6. Reply templates / prompt presets
Allow users to save prompt suffix presets (e.g., "Formal", "Casual", "Step-by-step") and switch between them via a dropdown near the Generate button. Currently the prompt suffix is only configurable in the Options page. Quick access to presets would let technicians adapt tone per-ticket.

### U7. Inline reply editing with diff view
When the user edits a generated reply, show a diff view (additions in green, removals in red) so they can see what they changed. This helps during review and also provides feedback data for model improvement.

### U8. Drag-to-resize for reply box
The reply text area has a fixed minimum height. Allow drag-to-resize so users can expand it when reviewing long replies. The edit textarea already has `resize: vertical` but the preview box does not.

### U9. Toast notification system for sidebar
Port the management SPA's toast system to the sidebar for consistent feedback. Replace scattered inline success/error messages with a unified toast that appears at the bottom of the sidebar.

### U10. Contextual insert target selector
Add a "Where to insert" dropdown in the sidebar that lets users choose between Tech Notes, Public Reply, or a custom selector. This would make the DOMInserter configurable at runtime without going to Options, addressing issue C5.

## Brainstorm: New Features

### F1. Reply quality scoring / confidence indicator
After generation, display a confidence score based on how many relevant KB articles were found, the similarity scores, and whether web search contributed context. A visual indicator (e.g., "High confidence - 3 KB matches" vs "Low confidence - no KB matches, consider adding articles") helps technicians decide how much to trust/edit the reply.

### F2. Ticket notes extraction
Read the "Notes" section from the WHD ticket DOM (the multi-row table with historical tech notes) and include it in the generation context. Previous technician notes often contain crucial troubleshooting history. Implementation: extend `DOMReader` with a `readNotes()` method that parses the notes table, add a `notes` field to `TicketData`, include in the generate request.

### F3. Quick reply suggestions
Before generating a full reply, show 3-4 one-line reply suggestions (like Gmail's Smart Reply) based on the ticket category and description. Users can click to expand any suggestion into a full reply. Implementation: a lightweight API endpoint that returns short completions, displayed as clickable chips above the Generate button.

### F4. Bulk ticket processing
For technicians handling queues of similar tickets (e.g., password resets), add a "Queue mode" that pre-generates replies for the next N tickets in a list. When the technician opens each ticket, the reply is already waiting. Implementation: a queue panel in the sidebar that accepts a list of ticket URLs, processes them in background, shows status per ticket.

### F5. Reply analytics dashboard
Track generation metrics over time: average generation latency, acceptance rate (inserted vs. discarded), edit distance (how much users modify generated replies), rating distribution. Display in the Management SPA. This data helps administrators tune the model, prompt, and KB content.

### F6. Similar ticket finder
When a technician opens a ticket, automatically search the ticket corpus for similar past tickets and show them in a collapsible panel. Display the ticket subject, resolution, and a "Use this reply" button that pre-fills the reply. Implementation: use the existing embedding infrastructure to search `whd_tickets` collection by the current ticket's description.

### F7. KB article suggestion from reply
After a technician writes or edits a reply that contains useful knowledge not in the KB, prompt them: "This looks like a useful solution. Save as a KB article?" One click creates a draft article pre-filled with the ticket context and reply. Implementation: a "Save to KB" button that appears when the reply is edited, calls the create article API.

### F8. Multi-language reply support
Add a language selector that translates the generated reply into the requester's preferred language. For international organizations, tickets may come in different languages but technicians may only speak one. Implementation: add a post-processing step that uses the LLM to translate, or detect the ticket language and generate directly in that language.

### F9. Canned responses library
A collection of pre-written responses for common scenarios (e.g., "Password reset instructions", "VPN setup guide") that technicians can insert with one click. Unlike generated replies, these are deterministic and pre-approved. Implementation: a new sidebar tab "Templates" with a searchable list, stored as KB articles with a `template` tag.

### F10. Ticket triage assistant
Before generating a reply, analyze the ticket and suggest: (a) priority level, (b) appropriate category if miscategorized, (c) whether it should be escalated, (d) estimated resolution time based on similar tickets. Display as a small card above the Generate button. This helps new technicians handle tickets they are unfamiliar with.

### F11. Collaborative annotations
Allow multiple technicians to annotate KB articles with tips, caveats, or "this is outdated" flags directly from the Management SPA. These annotations appear as inline notes when the article is used as context for generation. Implementation: a lightweight comment system on article detail, stored as metadata in ChromaDB.

### F12. Auto-detect and warn on stale KB articles
Track when KB articles were last used for successful reply generation (rating = good). Flag articles that have not contributed to any positively-rated reply in 90+ days as potentially stale. Show a "Review needed" badge in the Management SPA article list.
