import type { DOMReader } from './dom-reader'
import { OBSERVER_DEBOUNCE_MS } from '../shared/constants'

export class SidebarHost {
  private reader: DOMReader
  private observer: MutationObserver | null = null
  private debounceTimer: ReturnType<typeof setTimeout> | null = null

  constructor(reader: DOMReader) {
    this.reader = reader
  }

  start(): void {
    this.sendTicketData()
    this.startObserver()
  }

  stop(): void {
    if (this.observer) {
      this.observer.disconnect()
      this.observer = null
    }
    if (this.debounceTimer !== null) {
      clearTimeout(this.debounceTimer)
      this.debounceTimer = null
    }
  }

  private sendTicketData(): void {
    const data = this.reader.extract()
    if (data) {
      chrome.runtime.sendMessage({ type: 'TICKET_DATA_UPDATED', payload: data }).catch(() => {})
    } else {
      chrome.runtime.sendMessage({ type: 'NOT_A_TICKET_PAGE' }).catch(() => {})
    }
  }

  /**
   * Find the most specific observer target available in the WHD DOM.
   * Falls back through progressively broader ancestors before resorting
   * to document.body.
   */
  private findObserverTarget(): Element {
    const candidates = [
      '#ticketDetailForm',
      '#ticketDetail',
      '#mainContent',
      '.pageContent',
      'main',
    ]
    for (const selector of candidates) {
      const el = document.querySelector(selector)
      if (el) return el
    }
    return document.body
  }

  private startObserver(): void {
    this.observer = new MutationObserver(() => {
      // Debounce to avoid flooding on WHD's rapid partial DOM updates
      if (this.debounceTimer !== null) clearTimeout(this.debounceTimer)
      this.debounceTimer = setTimeout(() => {
        this.sendTicketData()
      }, OBSERVER_DEBOUNCE_MS)
    })

    const targetNode = this.findObserverTarget()
    this.observer.observe(targetNode, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['value', 'selected', 'class'],
      characterData: false,
    })

    // Ensure observer and timers are cleaned up when the page navigates away
    window.addEventListener('beforeunload', () => {
      this.stop()
    })
  }
}
