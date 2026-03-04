import { DEFAULT_BACKEND_URL, STORAGE_KEY_SETTINGS } from '../shared/constants'

/** Get the backend URL from settings (mirrors api-client logic). */
async function getBackendUrl(): Promise<string> {
  return new Promise((resolve) => {
    chrome.storage.sync.get(STORAGE_KEY_SETTINGS, (result) => {
      const settings = result[STORAGE_KEY_SETTINGS] as { backendUrl?: string } | undefined
      resolve(settings?.backendUrl ?? DEFAULT_BACKEND_URL)
    })
  })
}

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
