import { getBackendUrl } from './api-client'

/**
 * Detect whether a network error is likely caused by CORS rejection
 * rather than the backend being genuinely offline.
 *
 * Strategy: issue a `no-cors` fetch to the health endpoint. A `no-cors`
 * request always gets an opaque response (type "opaque", status 0) if
 * the server is reachable — even when CORS blocks regular requests.
 * If `no-cors` also throws, the server is truly unreachable.
 */
export async function isCorsProbablyBlocked(): Promise<boolean> {
  try {
    const base = await getBackendUrl()
    const resp = await fetch(`${base}/health`, {
      mode: 'no-cors',
      signal: AbortSignal.timeout(3000),
    })
    // An opaque response (type "opaque") means the server responded
    // but CORS headers are blocking the normal request.
    return resp.type === 'opaque'
  } catch {
    // Fetch itself failed — server is down, not a CORS issue
    return false
  }
}
