import type {
  ArticleListResponse,
  ArticleDetail,
  DeleteResponse,
  KBStats,
  HealthResponse,
  IngestUploadResponse,
  IngestUrlResponse,
  ArticleListParams,
  CreateArticleResponse,
  UpdateArticleResponse,
  UpdateTagsResponse,
  TagListResponse,
} from './types'
import { ApiError } from '@/shared/api-error'

export { ApiError }

interface AuthCheckResponse {
  authenticated: boolean
}

export async function login(token: string): Promise<boolean> {
  const resp = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
    credentials: 'same-origin',
  })
  return resp.ok
}

export async function checkSession(): Promise<boolean> {
  const resp = await fetch('/auth/check', {
    credentials: 'same-origin',
  })
  if (!resp.ok) return false
  const data = (await resp.json()) as AuthCheckResponse
  return data.authenticated
}

export async function logout(): Promise<void> {
  await fetch('/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
  })
}

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)whd_csrf=([^;]+)/)
  return match ? match[1] : ''
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}

  // Don't set Content-Type for FormData (browser sets multipart boundary)
  if (!(options?.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  // CSRF token for mutating requests (double-submit cookie pattern)
  const method = options?.method?.toUpperCase() ?? 'GET'
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
    const csrf = getCsrfToken()
    if (csrf) headers['X-CSRF-Token'] = csrf
  }

  const resp = await fetch(path, {
    ...options,
    headers: { ...headers, ...(options?.headers as Record<string, string>) },
    credentials: 'same-origin',
  })

  if (!resp.ok) {
    throw new ApiError(resp.status, await resp.json().catch(() => ({})))
  }

  return resp.json() as Promise<T>
}

export const managementApi = {
  listArticles(params: ArticleListParams): Promise<ArticleListResponse> {
    const qs = new URLSearchParams()
    qs.set('page', String(params.page))
    qs.set('page_size', String(params.page_size))
    if (params.search) qs.set('search', params.search)
    if (params.source_type) qs.set('source_type', params.source_type)
    return fetchApi<ArticleListResponse>(`/kb/articles?${qs.toString()}`)
  },

  getArticle(id: string): Promise<ArticleDetail> {
    return fetchApi<ArticleDetail>(`/kb/articles/${encodeURIComponent(id)}`)
  },

  deleteArticle(id: string): Promise<DeleteResponse> {
    return fetchApi<DeleteResponse>(`/kb/articles/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },

  getStats(): Promise<KBStats> {
    return fetchApi<KBStats>('/kb/stats')
  },

  uploadFile(file: File): Promise<IngestUploadResponse> {
    const form = new FormData()
    form.append('file', file)
    return fetchApi<IngestUploadResponse>('/ingest/upload', {
      method: 'POST',
      body: form,
    })
  },

  ingestUrl(url: string): Promise<IngestUrlResponse> {
    return fetchApi<IngestUrlResponse>('/ingest/url', {
      method: 'POST',
      body: JSON.stringify({ url }),
    })
  },

  getHealth(): Promise<HealthResponse> {
    return fetchApi<HealthResponse>('/health')
  },

  createArticle(title: string, content: string, tags: string[] = []): Promise<CreateArticleResponse> {
    return fetchApi<CreateArticleResponse>('/kb/articles', {
      method: 'POST',
      body: JSON.stringify({ title, content, tags }),
    })
  },

  updateArticle(id: string, title: string, content: string, tags: string[]): Promise<UpdateArticleResponse> {
    return fetchApi<UpdateArticleResponse>(`/kb/articles/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify({ title, content, tags }),
    })
  },

  updateTags(articleId: string, tags: string[]): Promise<UpdateTagsResponse> {
    return fetchApi<UpdateTagsResponse>(`/kb/articles/${encodeURIComponent(articleId)}/tags`, {
      method: 'PATCH',
      body: JSON.stringify({ tags }),
    })
  },

  getTags(): Promise<TagListResponse> {
    return fetchApi<TagListResponse>('/kb/tags')
  },
}
