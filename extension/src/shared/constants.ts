/** Default selector config for WHD DOM fields */
export const DEFAULT_SELECTORS = {
  subject: 'input#subject',
  subjectFallbacks: ['td.subject > span', 'h1'],

  description: 'textarea#problemDescription',
  descriptionFallbacks: ['div.problemDescription', '#ticketDescription'],

  requesterName: 'span#requestorName',
  requesterNameFallbacks: ['td[data-label="Requester"] span'],

  category: 'select#categoryName option:checked',
  categoryFallbacks: ['span.categoryName'],

  status: 'select#statusTypeId option:checked',
  statusFallbacks: ['span.statusName'],

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
export const TICKET_URL_PATTERNS = [/\/ticketDetail/, /\/tickets\/\d+/]

/** DOM markers that confirm we're on a ticket page */
export const TICKET_DOM_MARKERS = ['#ticketDetailForm', 'form[action*="ticketDetail"]']

/** Text sentinels that confirm ticket page content */
export const TICKET_CONTENT_SENTINELS = ['Ticket #', 'Tech Notes']
