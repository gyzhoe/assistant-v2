import type { FeedbackRequest, FeedbackResponse, GenerateRequest, GenerateResponse, HealthResponse, IngestUploadResponse, IngestUrlResponse, KBArticleListResponse, ModelDownloadStatus, ModelsResponse, SSEEvent } from '../shared/types'
import { parseSSEStream } from './sse-parser'
import { DEFAULT_BACKEND_URL, STORAGE_KEY_SETTINGS, STORAGE_KEY_SECRETS, NATIVE_HOST } from '../shared/constants'
import { ApiError } from '../shared/api-error'

export async function getBackendUrl(): Promise<string> {
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

  async generateStream(req: GenerateRequest, signal?: AbortSignal): Promise<AsyncGenerator<SSEEvent>> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/generate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ ...req, stream: true }),
      signal,
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new ApiError(resp.status, error)
    }
    if (!resp.body) {
      throw new ApiError(0, { detail: 'Response body is not readable' })
    }
    return parseSSEStream(resp.body.getReader(), signal)
  },

  async health(): Promise<HealthResponse> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    // /health/detail returns full info (LLM, chroma counts) behind auth.
    // On 401/403 (token not yet provisioned), fall back to unauthenticated /health.
    const detailResp = await fetch(`${base}/health/detail`, { headers, signal: AbortSignal.timeout(4000) })
    if (detailResp.ok) {
      return detailResp.json() as Promise<HealthResponse>
    }
    if (detailResp.status === 401 || detailResp.status === 403) {
      const basicResp = await fetch(`${base}/health`, { signal: AbortSignal.timeout(4000) })
      if (basicResp.ok) {
        const data = await basicResp.json() as { status: string; version?: string }
        return {
          status: data.status === 'ok' ? 'ok' : 'degraded',
          llm_reachable: false,
          chroma_ready: false,
          chroma_doc_counts: {},
          version: data.version ?? '',
        }
      }
    }
    throw new ApiError(detailResp.status, { detail: 'Health check failed' })
  },

  async shutdown(): Promise<void> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    // Server may die before responding — use a short timeout and ignore errors
    await fetch(`${base}/shutdown`, { method: 'POST', headers, signal: AbortSignal.timeout(2000) }).catch(() => {})
  },

  async llmStart(): Promise<{ status: string }> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/llm/start`, { method: 'POST', headers })
    if (!resp.ok) throw new ApiError(resp.status, { detail: 'Failed to start LLM server' })
    return resp.json() as Promise<{ status: string }>
  },

  async llmStop(): Promise<{ status: string }> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/llm/stop`, { method: 'POST', headers })
    if (!resp.ok) throw new ApiError(resp.status, { detail: 'Failed to stop LLM server' })
    return resp.json() as Promise<{ status: string }>
  },

  async models(): Promise<ModelsResponse> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/models`, { headers })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Failed to fetch models' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<ModelsResponse>
  },

  async switchModel(model: string): Promise<{ status: string; model: string }> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/llm/switch`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ model }),
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Failed to switch model' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<{ status: string; model: string }>
  },

  async downloadModels(models?: string[]): Promise<{ status: string; models: string[] }> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/models/download`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ models: models ?? [] }),
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Failed to start download' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<{ status: string; models: string[] }>
  },

  async downloadStatus(): Promise<ModelDownloadStatus> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/models/download/status`, { headers })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Failed to get download status' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<ModelDownloadStatus>
  },

  async cancelDownload(): Promise<{ status: string }> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/models/download/cancel`, { method: 'POST', headers })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Failed to cancel download' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<{ status: string }>
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

  async submitFeedback(data: FeedbackRequest): Promise<FeedbackResponse> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/feedback`, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<FeedbackResponse>
  },

  async deleteFeedback(docId: string): Promise<void> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/feedback/${encodeURIComponent(docId)}`, {
      method: 'DELETE',
      headers,
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new ApiError(resp.status, error)
    }
  },

  async searchKBArticles(query: string, limit: number = 5, page: number = 1, signal?: AbortSignal): Promise<KBArticleListResponse> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const params = new URLSearchParams({ search: query, page_size: String(limit), page: String(page) })
    const resp = await fetch(`${base}/kb/articles?${params.toString()}`, { headers, signal })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<KBArticleListResponse>
  },

  async ingestUrl(url: string, signal?: AbortSignal): Promise<IngestUrlResponse> {
    const [base, headers] = await Promise.all([getBackendUrl(), buildHeaders()])
    const resp = await fetch(`${base}/ingest/url`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ url }),
      signal,
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new ApiError(resp.status, error)
    }
    return resp.json() as Promise<IngestUrlResponse>
  },
}

interface NativeResponse {
  ok: boolean
  status?: string
  error?: string
  token?: string
  llm_started?: boolean
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

export { ApiError } from '../shared/api-error'
