import { debugError } from '../shared/constants'

/** Safe querySelector that catches SyntaxError from invalid CSS selectors. */
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

export class DOMInserter {
  private readonly techNotesSelectors = [
    'textarea#techNotes',
    'textarea[name="techNote"]',
    '#techNotesDiv textarea',
  ]

  private customSelector = ''

  /** Set a user-configured override selector that takes priority over defaults. */
  setCustomSelector(selector: string): void {
    this.customSelector = selector.trim()
  }

  /**
   * Inserts text into the WHD reply textarea.
   * Uses the native setter trick to bypass React/framework value caching.
   * Returns true on success, false if textarea not found.
   */
  insertReply(text: string): boolean {
    const textarea = this.findTextarea()
    if (!textarea) return false

    // Native setter trick — bypasses framework value caching
    const nativeSetter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      'value'
    )?.set

    if (nativeSetter) {
      nativeSetter.call(textarea, text)
    } else {
      textarea.value = text
    }

    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    textarea.dispatchEvent(new Event('change', { bubbles: true }))

    // Scroll into view and focus
    textarea.scrollIntoView({ behavior: 'smooth', block: 'center' })
    textarea.focus()

    return true
  }

  private findTextarea(): HTMLTextAreaElement | null {
    // Try user-configured selector first (may be invalid — use safe wrapper)
    if (this.customSelector) {
      const el = safeQuerySelector(this.customSelector)
      if (el instanceof HTMLTextAreaElement) return el
    }

    // Fall back to built-in selectors
    for (const sel of this.techNotesSelectors) {
      const el = safeQuerySelector(sel)
      if (el instanceof HTMLTextAreaElement) return el
    }
    return null
  }
}
