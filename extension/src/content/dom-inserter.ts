export class DOMInserter {
  private readonly techNotesSelectors = [
    'textarea#techNotes',
    'textarea[name="techNote"]',
    '#techNotesDiv textarea',
  ]

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
    for (const sel of this.techNotesSelectors) {
      const el = document.querySelector(sel)
      if (el instanceof HTMLTextAreaElement) return el
    }
    return null
  }
}
