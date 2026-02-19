import type { TicketData, SelectorConfig, AppSettings } from '../shared/types'
import {
  DEFAULT_SELECTORS,
  TICKET_URL_PATTERNS,
  TICKET_DOM_MARKERS,
  TICKET_CONTENT_SENTINELS,
  STORAGE_KEY_SETTINGS,
} from '../shared/constants'

export class DOMReader {
  private overrides: Partial<SelectorConfig> = {}

  constructor() {
    // Load overrides from app settings asynchronously; extraction uses defaults until loaded
    this.loadOverrides()
  }

  private loadOverrides(): void {
    chrome.storage.sync.get(STORAGE_KEY_SETTINGS, (result) => {
      const saved = result[STORAGE_KEY_SETTINGS] as Partial<AppSettings> | undefined
      this.overrides = saved?.selectorOverrides ?? {}
    })
  }

  /** Returns true if the current page is a WHD ticket page. */
  isTicketPage(): boolean {
    const url = window.location.href

    // Tier 1: URL pattern
    if (TICKET_URL_PATTERNS.some((p) => p.test(url))) return true

    // Tier 2: DOM marker
    if (TICKET_DOM_MARKERS.some((sel) => document.querySelector(sel) !== null)) return true

    // Tier 3: Content sentinel
    const bodyText = document.body?.innerText ?? ''
    if (TICKET_CONTENT_SENTINELS.every((sentinel) => bodyText.includes(sentinel))) return true

    return false
  }

  /** Extracts ticket data from the DOM. Returns null if not a ticket page. */
  extract(): TicketData | null {
    if (!this.isTicketPage()) return null

    return {
      subject: this.readField('subject', DEFAULT_SELECTORS.subject, DEFAULT_SELECTORS.subjectFallbacks),
      description: this.readField('description', DEFAULT_SELECTORS.description, DEFAULT_SELECTORS.descriptionFallbacks),
      requesterName: this.readField('requesterName', DEFAULT_SELECTORS.requesterName, DEFAULT_SELECTORS.requesterNameFallbacks),
      category: this.readField('category', DEFAULT_SELECTORS.category, DEFAULT_SELECTORS.categoryFallbacks),
      status: this.readField('status', DEFAULT_SELECTORS.status, DEFAULT_SELECTORS.statusFallbacks),
      ticketUrl: window.location.href,
    }
  }

  private readField(
    field: keyof SelectorConfig,
    primary: string,
    fallbacks: readonly string[]
  ): string {
    const override = this.overrides[field]
    const selectors = override ? [override, primary, ...fallbacks] : [primary, ...fallbacks]

    for (const sel of selectors) {
      const el = document.querySelector(sel)
      if (el) {
        const text = this.extractText(el)
        if (text) return text
      }
    }
    return ''
  }

  private extractText(el: Element): string {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      return el.value.trim()
    }
    if (el instanceof HTMLSelectElement) {
      return el.options[el.selectedIndex]?.text?.trim() ?? ''
    }
    return el.textContent?.trim() ?? ''
  }
}
