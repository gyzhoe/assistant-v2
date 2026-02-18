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

  private startObserver(): void {
    this.observer = new MutationObserver(() => {
      // Debounce to avoid flooding on WHD's rapid partial DOM updates
      if (this.debounceTimer !== null) clearTimeout(this.debounceTimer)
      this.debounceTimer = setTimeout(() => {
        this.sendTicketData()
      }, OBSERVER_DEBOUNCE_MS)
    })

    this.observer.observe(document.body, {
      childList: true,
      subtree: true,
    })
  }
}
