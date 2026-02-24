/** Default selector config for WHD DOM fields */
export const DEFAULT_SELECTORS = {
  subject: 'input#subject',
  subjectFallbacks: [
    'input#shortSubject',
    '#shortSubject',
    'td.subject > span',
    'h1',
    '.pageTitle',
    // WHD table-layout: first ProblemType select is often the effective subject
    'select[id^="ProblemType_"] option:checked',
  ],

  description: 'textarea#problemDescription',
  descriptionFallbacks: [
    'textarea#requestDetail',
    '#requestDetail',
    'div.problemDescription',
    '#ticketDescription',
    'textarea#detail',
    '#detail',
  ],

  requesterName: 'span#requestorName',
  requesterNameFallbacks: [
    'td[data-label="Requester"] span',
    'td[data-label="Client"] a',
    'a[href*="ClientActions"]',
    // WHD table-layout: client name in .defaultFont cell
    'td.defaultFont',
  ],

  category: 'select#categoryName option:checked',
  categoryFallbacks: [
    'span.categoryName',
    'select#requestTypeName option:checked',
    // WHD table-layout: ProblemType selects with dynamic IDs
    'select[id^="ProblemType_"] option:checked',
  ],

  status: 'select#statusTypeId option:checked',
  statusFallbacks: [
    'span.statusName',
    'select#statustype option:checked',
    'select[name*="status"] option:checked',
    // WHD table-layout: status search popup
    'select#statusSearchPopup option:checked',
  ],

  techNotes: 'textarea#techNotes',
  techNotesFallbacks: ['textarea[name="techNote"]', '#techNotesDiv textarea'],
} as const

/** chrome.storage.sync key for selector overrides */
export const STORAGE_KEY_SELECTOR_OVERRIDES = 'selectorOverrides'

/** chrome.storage.sync key for app settings */
export const STORAGE_KEY_SETTINGS = 'appSettings'

/**
 * chrome.storage.LOCAL key for security secrets (API token).
 * Uses local (not sync) so credentials are never synced to other devices.
 */
export const STORAGE_KEY_SECRETS = 'localSecrets'

/** Default backend URL */
export const DEFAULT_BACKEND_URL = 'http://localhost:8765'

/** Default LLM model */
export const DEFAULT_MODEL = 'llama3.2:3b'

/** MutationObserver debounce delay in ms */
export const OBSERVER_DEBOUNCE_MS = 300

/** Ticket URL detection patterns */
export const TICKET_URL_PATTERNS = [/\/ticketDetail/, /\/tickets\/\d+/, /\/TicketActions\/view\?ticket=/]

/** DOM markers that confirm we're on a ticket page */
export const TICKET_DOM_MARKERS = ['#ticketDetailForm', 'form[action*="ticketDetail"]', 'form[action*="TicketActions"]']

/** Text sentinels that confirm ticket page content */
export const TICKET_CONTENT_SENTINELS = ['Ticket Details', 'Tech']

/** Gated debug logger — silent in production builds */
export function debugLog(...args: unknown[]): void {
  if (import.meta.env.DEV) {
    console.log('[AI-HD]', ...args)
  }
}

/** Gated error logger — silent in production builds */
export function debugError(...args: unknown[]): void {
  if (import.meta.env.DEV) {
    console.error('[AI-HD]', ...args)
  }
}
