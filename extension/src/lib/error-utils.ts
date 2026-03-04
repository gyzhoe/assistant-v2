/**
 * Shared error detail parser.
 *
 * Extracts a human-readable message from arbitrary API error response bodies.
 * Handles plain strings, nested objects, Pydantic validation arrays, and
 * prevents `[object Object]` from ever reaching the UI.
 */

/** Recursively extract a readable string from an unknown value. */
function extractMessage(value: unknown, seen?: Set<unknown>): string | null {
  if (typeof value === 'string' && value.length > 0) return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value == null) return null

  // Guard against circular references
  const visited = seen ?? new Set<unknown>()
  if (visited.has(value)) return null
  visited.add(value)

  if (Array.isArray(value)) {
    // Pydantic validation: [{loc: [...], msg: "..."}, ...]
    const messages = value
      .map((item: unknown) => {
        if (typeof item === 'object' && item !== null && 'msg' in item) {
          const rec = item as Record<string, unknown>
          const loc = Array.isArray(rec['loc']) ? (rec['loc'] as unknown[]).join(' -> ') : ''
          const msg = typeof rec['msg'] === 'string' ? rec['msg'] : ''
          return loc ? `${loc}: ${msg}` : msg
        }
        return extractMessage(item, visited)
      })
      .filter(Boolean)
    if (messages.length > 0) return messages.join('; ')
    return null
  }

  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>
    // Prefer well-known keys in priority order
    for (const key of ['message', 'detail', 'error', 'msg']) {
      const extracted = extractMessage(obj[key], visited)
      if (extracted) return extracted
    }
    // Fallback: try all remaining string/array values (skip metadata keys)
    for (const [k, v] of Object.entries(obj)) {
      if (k === 'error_code' || k === 'type' || k === 'loc') continue
      const extracted = extractMessage(v, visited)
      if (extracted) return extracted
    }
  }

  return null
}

/**
 * Parse an API error response body into a user-friendly string.
 *
 * @param body - The parsed JSON body from an error response.
 * @returns A human-readable error message. Never returns `[object Object]`.
 */
export function parseErrorDetail(body: Record<string, unknown> | null | undefined): string {
  if (!body || typeof body !== 'object') return 'An unexpected error occurred'

  // Include error_code prefix when available
  const errorCode = typeof body['error_code'] === 'string' ? body['error_code'] : null

  const message = extractMessage(body)

  if (message) {
    return errorCode ? `[${errorCode}] ${message}` : message
  }

  return 'An unexpected error occurred'
}
