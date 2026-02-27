import type { GenerateRequest, GenerateResponse, HealthResponse, IngestUploadResponse } from '../shared/types'
import { DEFAULT_BACKEND_URL, STORAGE_KEY_SETTINGS, STORAGE_KEY_SECRETS } from '../shared/constants'

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
  async generate(req: GenerateRequest, signal?: AbortSignal): Promise<GenerateResponse> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/generate`, {
      method: 'POST',
      headers,
      body: JSON.stringify(req),
      signal,
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
    const resp = await fetch(`${base}/health`, { signal: AbortSignal.timeout(4000) })
    if (!resp.ok) throw new ApiError(resp.status, { detail: 'Health check failed' })
    return resp.json() as Promise<HealthResponse>
  },

  async shutdown(): Promise<void> {
    const base = await getBackendUrl()
    // Server may die before responding — use a short timeout and ignore errors
    await fetch(`${base}/shutdown`, { method: 'POST', signal: AbortSignal.timeout(2000) }).catch(() => {})
  },

  async ollamaStart(): Promise<{ status: string }> {
    const base = await getBackendUrl()
    const resp = await fetch(`${base}/ollama/start`, { method: 'POST' })
    if (!resp.ok) throw new ApiError(resp.status, { detail: 'Failed to start Ollama' })
    return resp.json() as Promise<{ status: string }>
  },

  async ollamaStop(): Promise<{ status: string }> {
    const base = await getBackendUrl()
    const resp = await fetch(`${base}/ollama/stop`, { method: 'POST' })
    if (!resp.ok) throw new ApiError(resp.status, { detail: 'Failed to stop Ollama' })
    return resp.json() as Promise<{ status: string }>
  },

  async models(): Promise<string[]> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/models`, { headers })
    if (!resp.ok) throw new ApiError(resp.status, { detail: 'Failed to fetch models' })
    const data = (await resp.json()) as { models: string[] }
    return data.models
  },

  async uploadFile(file: File, signal?: AbortSignal): Promise<IngestUploadResponse> {
    const [base, token] = await Promise.all([getBackendUrl(), getApiToken()])
    const form = new FormData()
    form.append('file', file)
    const headers: Record<string, string> = {}
    if (token) headers['X-Extension-Token'] = token
    const resp = await fetch(`${base}/ingest/upload`, {
      method: 'POST',
      headers,
      body: form,
      signal,
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<IngestUploadResponse>
  },

  async clearCollection(name: string): Promise<void> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/ingest/collections/${name}/clear`, {
      method: 'POST',
      headers,
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new ApiError(resp.status, error)
    }
  },
}

const NATIVE_HOST = 'com.assistant.backend_manager'

interface NativeResponse {
  ok: boolean
  status?: string
  error?: string
}

/** Send a command to the native messaging host to start a service. */
export function sendNativeCommand(action: string): Promise<NativeResponse> {
  return new Promise((resolve) => {
    chrome.runtime.sendNativeMessage(NATIVE_HOST, { action }, (response: NativeResponse) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message })
      } else {
        resolve(response)
      }
    })
  })
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown
  ) {
    super(`API error ${status}`)
  }
}
