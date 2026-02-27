import type { TicketData, SelectorConfig, AppSettings } from '../shared/types'
import {
  DEFAULT_SELECTORS,
  TICKET_URL_PATTERNS,
  TICKET_DOM_MARKERS,
  TICKET_CONTENT_SENTINELS,
  STORAGE_KEY_SETTINGS,
  debugError,
} from '../shared/constants'

/**
 * WHD label-text → field mapping.
 * Used as a last-resort fallback when CSS selectors don't match.
 * The reader scans `td.labelStandard` cells for these labels,
 * then extracts the value from the adjacent cell in the same row.
 */
const WHD_LABELS: Record<string, readonly string[]> = {
  subject: ['Subject', 'Short Subject'],
  description: ['Request Detail', 'Problem Description', 'Detail'],
  requesterName: ['Client', 'Requester', 'Requested By'],
  category: ['Request Type', 'Category', 'Problem Type'],
  status: ['Status'],
}

/**
 * Safe wrapper around document.querySelector that catches SyntaxError
 * thrown by invalid CSS selectors (e.g. user-supplied overrides from options page).
 * Returns null and logs the error instead of crashing the content script.
 */
function safeQuerySelector(selector: string): Element | null {
  try {
    return document.querySelector(selector)
  } catch (err) {
    if (err instanceof SyntaxError) {
      debugError('Invalid CSS selector skipped:', selector, err.message)
      return null
    }
    throw err
  }
}

export class DOMReader {
  private overrides: Partial<SelectorConfig> = {}
  private readonly _ready: Promise<void>

  constructor() {
    this._ready = this.loadOverrides()
  }

  private loadOverrides(): Promise<void> {
    return new Promise<void>((resolve) => {
      chrome.storage.sync.get(STORAGE_KEY_SETTINGS, (result) => {
        const saved = result[STORAGE_KEY_SETTINGS] as Partial<AppSettings> | undefined
        this.overrides = saved?.selectorOverrides ?? {}
        resolve()
      })
    })
  }

  /** Wait until selector overrides are loaded from storage. */
  async ready(): Promise<void> {
    await this._ready
  }

  /** Returns true if the current page is a WHD ticket page. */
  isTicketPage(): boolean {
    const url = window.location.href

    if (TICKET_URL_PATTERNS.some((p) => p.test(url))) return true
    if (TICKET_DOM_MARKERS.some((sel) => safeQuerySelector(sel) !== null)) return true

    const bodyText = document.body?.innerText ?? ''
    if (TICKET_CONTENT_SENTINELS.every((sentinel) => bodyText.includes(sentinel))) return true

    return false
  }

  /** Extracts ticket data from the DOM. Returns null if not a ticket page. */
  extract(): TicketData | null {
    if (!this.isTicketPage()) return null

    const subject = this.readField('subject', DEFAULT_SELECTORS.subject, DEFAULT_SELECTORS.subjectFallbacks)
    const category = this.readField('category', DEFAULT_SELECTORS.category, DEFAULT_SELECTORS.categoryFallbacks)

    return {
      // If no explicit subject field exists, use the request type (common in WHD)
      subject: subject || category || this.extractSubjectFromTitle(),
      description: this.readField('description', DEFAULT_SELECTORS.description, DEFAULT_SELECTORS.descriptionFallbacks),
      requesterName: this.readField('requesterName', DEFAULT_SELECTORS.requesterName, DEFAULT_SELECTORS.requesterNameFallbacks),
      category,
      status: this.readField('status', DEFAULT_SELECTORS.status, DEFAULT_SELECTORS.statusFallbacks),
      ticketUrl: window.location.href,
      customFields: this.readCustomFields(),
    }
  }

  private readField(
    field: keyof SelectorConfig,
    primary: string,
    fallbacks: readonly string[]
  ): string {
    const override = this.overrides[field]
    const selectors = override ? [override, primary, ...fallbacks] : [primary, ...fallbacks]

    // Tier 1: CSS selectors
    for (const sel of selectors) {
      const el = safeQuerySelector(sel)
      if (el) {
        const text = this.extractText(el)
        if (text) return text
      }
    }

    // Tier 2: WHD label-based extraction (table layout)
    const labels = WHD_LABELS[field]
    if (labels) {
      const result = this.readByLabel(labels)
      if (result) return result
    }

    return ''
  }

  /**
   * Label-based extraction for WHD's table layout.
   * Finds `td.labelStandard` cells matching the target text,
   * then reads the value from the adjacent data cell.
   */
  private readByLabel(labelTexts: readonly string[]): string {
    const allLabels = document.querySelectorAll('td.labelStandard')

    for (const labelCell of allLabels) {
      const cellText = labelCell.textContent?.trim()
      if (!cellText || !labelTexts.some((t) => cellText === t)) continue

      // Strategy 1: scan sibling TDs in the same row
      const row = labelCell.closest('tr')
      if (row) {
        const cells = row.querySelectorAll('td:not(.labelStandard)')
        for (const cell of cells) {
          const val = this.extractValueFromCell(cell)
          if (val) return val
        }
      }

      // Strategy 2: next sibling elements (for non-standard row layouts)
      let sibling = labelCell.nextElementSibling
      while (sibling) {
        if (sibling.tagName === 'TD' || sibling.tagName === 'DIV') {
          const val = this.extractValueFromCell(sibling)
          if (val) return val
        }
        sibling = sibling.nextElementSibling
      }

      // Strategy 3: look at the next table row (some WHD layouts split label/value across rows)
      const nextRow = row?.nextElementSibling
      if (nextRow?.tagName === 'TR') {
        const cells = nextRow.querySelectorAll('td')
        for (const cell of cells) {
          const val = this.extractValueFromCell(cell)
          if (val) return val
        }
      }
    }
    return ''
  }

  /** Extract a meaningful value from a table cell, preferring interactive elements. */
  private extractValueFromCell(cell: Element): string {
    // Prefer interactive elements inside the cell
    const select = cell.querySelector('select')
    if (select) return this.extractText(select)

    const textarea = cell.querySelector('textarea')
    if (textarea) return this.extractText(textarea)

    const input = cell.querySelector('input:not([type="hidden"]):not([type="submit"])')
    if (input) return this.extractText(input)

    // Fall back to the cell's own text, ignoring label-like cells
    const text = cell.textContent?.trim() ?? ''
    if (text && !cell.classList.contains('labelStandard')) return text

    return ''
  }

  /** Try to extract a ticket subject from document.title. */
  private extractSubjectFromTitle(): string {
    const title = document.title?.trim() ?? ''
    // Common WHD title formats: "Web Help Desk - Ticket #105733 - Subject Here"
    const match = title.match(/(?:ticket\s*#?\d+\s*[-–—]\s*)(.+)/i)
      ?? title.match(/[-–—]\s*(.+)$/)
    return match?.[1]?.trim() ?? ''
  }

  /**
   * Extract all custom fields from the WHD "Custom Fields" section.
   * Scans for label/value pairs in the table layout.
   */
  private readCustomFields(): Record<string, string> {
    const fields: Record<string, string> = {}
    const allLabels = document.querySelectorAll('td.labelStandard')

    let inCustomSection = false
    for (const labelCell of allLabels) {
      const cellText = labelCell.textContent?.trim() ?? ''

      if (cellText === 'Custom Fields') {
        inCustomSection = true
        continue
      }

      if (!inCustomSection || !cellText) continue

      const row = labelCell.closest('tr')
      if (!row) continue
      const cells = row.querySelectorAll('td:not(.labelStandard)')
      for (const cell of cells) {
        const val = this.extractValueFromCell(cell)
        if (val) {
          fields[cellText] = val
          break
        }
      }
    }

    return fields
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
