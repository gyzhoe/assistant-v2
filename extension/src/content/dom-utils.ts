import { debugError } from '../shared/constants'

/**
 * Safe wrapper around document.querySelector that catches SyntaxError
 * thrown by invalid CSS selectors (e.g. user-supplied overrides from options page).
 * Returns null and logs the error instead of crashing the content script.
 */
export function safeQuerySelector(selector: string): Element | null {
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
