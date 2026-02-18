import type { GenerateRequest, GenerateResponse, HealthResponse } from '../shared/types'
import { DEFAULT_BACKEND_URL, STORAGE_KEY_SETTINGS } from '../shared/constants'

const STORAGE_KEY_SECRETS = 'localSecrets'

async function getBackendUrl(): Promise<string> {
  return new Promise((resolve) => {
    chrome.storage.sync.get(STORAGE_KEY_SETTINGS, (result) => {
      const settings = result[STORAGE_KEY_SETTINGS] as { backendUrl?: string } | undefined
      resolve(settings?.backendUrl ?? DEFAULT_BACKEND_URL)
    })
  })
}

/** Reads the API token from chrome.storage.local (device-only, never synced). */
async function getApiToken(): Promise<string> {
  return new Promise((resolve) => {
    chrome.storage.local.get(STORAGE_KEY_SECRETS, (result) => {
      const secrets = result[STORAGE_KEY_SECRETS] as { apiToken?: string } | undefined
      resolve(secrets?.apiToken ?? '')
    })
  })
}

/** Builds headers including the X-Extension-Token when a token is configured. */
async function buildHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  const token = await getApiToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...extra }
  if (token) headers['X-Extension-Token'] = token
  return headers
}

export const apiClient = {
  async generate(req: GenerateRequest): Promise<GenerateResponse> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/generate`, {
      method: 'POST',
      headers,
      body: JSON.stringify(req),
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<GenerateResponse>
  },

  async health(): Promise<HealthResponse> {
    const base = await getBackendUrl()
    // /health is exempt from token auth — no token sent
    const resp = await fetch(`${base}/health`)
    if (!resp.ok) throw new ApiError(resp.status, { detail: 'Health check failed' })
    return resp.json() as Promise<HealthResponse>
  },

  async models(): Promise<string[]> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/models`, { headers })
    if (!resp.ok) throw new ApiError(resp.status, { detail: 'Failed to fetch models' })
    const data = (await resp.json()) as { models: string[] }
    return data.models
  },
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown
  ) {
    super(`API error ${status}`)
  }
}
