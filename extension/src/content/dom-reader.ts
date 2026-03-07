import type { TicketData, NoteData, SelectorConfig, AppSettings } from '../shared/types'
import {
  DEFAULT_SELECTORS,
  TICKET_URL_PATTERNS,
  TICKET_DOM_MARKERS,
  TICKET_CONTENT_SENTINELS,
  STORAGE_KEY_SETTINGS,
} from '../shared/constants'
import { safeQuerySelector } from './dom-utils'

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
      notes: this.readNotes(),
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

    // Radio button group: return the label of the checked radio
    const radios = cell.querySelectorAll('input[type="radio"]')
    if (radios.length > 0) {
      const checked = Array.from(radios).find((r) => (r as HTMLInputElement).checked) as HTMLInputElement | undefined
      if (checked) {
        // Try <label for="id">, then adjacent text node
        const label = checked.id ? cell.querySelector(`label[for="${checked.id}"]`) : null
        if (label) return label.textContent?.trim() ?? ''
        let next: ChildNode | null = checked.nextSibling
        while (next) {
          if (next.nodeType === Node.TEXT_NODE && next.textContent?.trim()) return next.textContent.trim()
          next = next.nextSibling
        }
      }
      return ''
    }

    const input = cell.querySelector('input:not([type="hidden"]):not([type="submit"]):not([type="radio"])')
    if (input) return this.extractText(input)

    // WHD pattern: td.dataStandard cells contain the value in the first <div>
    // and a help-text description in subsequent <div>s. Read only the first
    // child <div> to avoid including the description paragraph.
    const childDivs = cell.querySelectorAll(':scope > div')
    if (childDivs.length > 1) {
      const firstDiv = childDivs[0]
      const text = firstDiv.textContent?.trim() ?? ''
      if (text) return text
    }

    // Fall back to the cell's own text, ignoring label-like cells
    const clone = cell.cloneNode(true) as Element
    clone.querySelectorAll('script, style, noscript').forEach((s) => s.remove())
    const text = clone.textContent?.trim() ?? ''
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
   * WHD renders custom fields inside `div#CustomFieldsPanelDiv` with
   * standard label/value table rows. Falls back to scanning all
   * `td.labelStandard` cells after the "Custom Fields" header.
   */
  private readCustomFields(): Record<string, string> {
    const fields: Record<string, string> = {}

    // Primary: use the dedicated custom fields container
    const cfPanel = document.getElementById('CustomFieldsPanelDiv')
    if (cfPanel) {
      const labels = cfPanel.querySelectorAll('td.labelStandard')
      for (const labelCell of labels) {
        const name = labelCell.textContent?.trim() ?? ''
        if (!name) continue
        const row = labelCell.closest('tr')
        if (!row) continue
        const cells = row.querySelectorAll('td:not(.labelStandard)')
        for (const cell of cells) {
          const val = this.extractValueFromCell(cell)
          if (val) {
            fields[name] = val
            break
          }
        }
      }
      return fields
    }

    // Fallback: scan all td.labelStandard after a "Custom Fields" marker
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

  /**
   * Extract notes from the WHD Notes section.
   * Each note spans 3 <tr> rows; the main row has class 'white' or 'shaded'.
   */
  private readNotes(): NoteData[] {
    const notes: NoteData[] = []
    const container = document.querySelector('div#NotesPanelDiv table.alternatingRowColor.contextArea')
    if (!container) return notes

    const rows = container.querySelectorAll('tr.white, tr.shaded')
    for (const row of rows) {
      const cells = row.querySelectorAll('td')
      if (cells.length < 8) continue

      // Date+time from cell[0]
      const dateRaw = cells[0].textContent?.trim().replace(/\s+/g, ' ') ?? ''

      // Author from cell[1]
      const author = cells[1].textContent?.trim() ?? ''

      // Note text from cell[2] (noteListCell)
      const noteCell = row.querySelector('td.noteListCell')
      let noteText = ''
      let noteId = ''
      if (noteCell) {
        const noteDiv = noteCell.querySelector('div')
        if (noteDiv) {
          const clone = noteDiv.cloneNode(true) as Element
          clone.querySelectorAll('a, script, style, noscript, abbr').forEach((el) => el.remove())
          noteText = clone.textContent?.trim().replace(/\s+/g, ' ').replace(/\d+\s+\w+\s+ago\s*/gi, '').trim() ?? ''
        }
        const noteAnchor = noteCell.querySelector('a[href*="#"]')
        noteId = noteAnchor ? noteAnchor.getAttribute('href')?.split('#').pop() ?? '' : ''
      }

      // Type detection via decoration cells
      let type: NoteData['type'] = 'client'
      if (row.querySelector('td.noteBodyBlue, td.noteTopBlue, td.noteCornerBlue')) {
        type = 'tech_visible'
      } else if (row.querySelector('td.noteBodyGray, td.noteTopGray, td.noteCornerGray')) {
        type = 'tech_internal'
      }

      // Time spent from cell[6]
      const timeSpent = cells[6]?.textContent?.trim() ?? ''

      if (noteText || author) {
        notes.push({ author, text: noteText, type, date: dateRaw, noteId, timeSpent })
      }
    }

    return notes
  }

  private extractText(el: Element): string {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      return el.value.trim()
    }
    if (el instanceof HTMLSelectElement) {
      return el.options[el.selectedIndex]?.text?.trim() ?? ''
    }
    const clone = el.cloneNode(true) as Element
    clone.querySelectorAll('script, style, noscript').forEach((s) => s.remove())
    return clone.textContent?.trim() ?? ''
  }
}
