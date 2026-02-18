# WHD DOM Selectors — Living Document

This document tracks confirmed CSS selectors for SolarWinds Web Help Desk fields.
**Update this file whenever selectors are confirmed or changed on a specific WHD version.**

## Ticket Detection (3-tier)

| Tier | Method | Value |
|---|---|---|
| 1 | URL pattern | `/ticketDetail`, `/tickets/\d+` |
| 2 | DOM marker | `#ticketDetailForm`, `form[action*="ticketDetail"]` |
| 3 | Content sentinel | Page text contains "Ticket #" AND "Tech Notes" |

All three tiers are checked in order. If any passes, the page is treated as a ticket page.

## Field Selectors (with fallback chains)

| Field | Primary | Fallback 1 | Fallback 2 |
|---|---|---|---|
| Subject | `input#subject` | `td.subject > span` | `h1` |
| Description | `textarea#problemDescription` | `div.problemDescription` | `#ticketDescription` |
| Requester | `span#requestorName` | `td[data-label="Requester"] span` | — |
| Category | `select#categoryName option:checked` | `span.categoryName` | — |
| Status | `select#statusTypeId option:checked` | `span.statusName` | — |
| Reply textarea | `textarea#techNotes` | `textarea[name="techNote"]` | `#techNotesDiv textarea` |

## Overriding Selectors

Selectors are stored in `chrome.storage.sync` under the key `selectorOverrides`.
To override a selector for your WHD installation without rebuilding the extension:

1. Open the extension options page
2. Navigate to "DOM Selector Overrides"
3. Paste your custom CSS selector for each field

Or programmatically (from DevTools console on a WHD page):
```javascript
chrome.storage.sync.set({
  selectorOverrides: {
    subject: 'your-custom-selector',
    techNotes: 'your-textarea-selector'
  }
})
```

## WHD Version Compatibility

| WHD Version | Tested | Notes |
|---|---|---|
| 12.x | Pending | Initial target version |

## Known Issues

- WHD uses WebObjects for partial page refreshes — DOM may change without navigation
- MutationObserver is debounced 300ms to prevent flooding on rapid DOM changes
- Some WHD installations use iframes for the reply area — check `sidebar-host.ts` if selectors fail

## Updating This Document

When you confirm a new selector or find a selector change:
1. Update the table above with the confirmed selector
2. Note the WHD version tested against
3. Commit with message: `docs: update WHD DOM selectors for WHD vX.Y`
