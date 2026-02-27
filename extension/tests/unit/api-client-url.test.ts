import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome.storage
vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: vi.fn((_keys: string, cb: (result: Record<string, unknown>) => void) => cb({})),
    },
    local: {
      get: vi.fn((_keys: string, cb: (result: Record<string, unknown>) => void) => cb({})),
    },
  },
})

// Mock fetch
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('apiClient.ingestUrl', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls /ingest/url with correct body', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        url: 'https://example.com',
        collection: 'kb_articles',
        chunks_ingested: 5,
        processing_time_ms: 1200,
        title: 'Example Page',
        warning: null,
      }),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    const result = await apiClient.ingestUrl('https://example.com')

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8765/ingest/url',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ url: 'https://example.com' }),
      })
    )
    expect(result.chunks_ingested).toBe(5)
    expect(result.title).toBe('Example Page')
  })

  it('throws ApiError on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'SSRF blocked' }),
    })

    const { apiClient, ApiError } = await import('../../src/lib/api-client')
    await expect(apiClient.ingestUrl('http://localhost')).rejects.toBeInstanceOf(ApiError)
  })

  it('includes auth header when token is set', async () => {
    vi.resetModules()

    vi.stubGlobal('chrome', {
      storage: {
        sync: {
          get: vi.fn((_keys: string, cb: (result: Record<string, unknown>) => void) => cb({})),
        },
        local: {
          get: vi.fn((_keys: string, cb: (result: Record<string, unknown>) => void) =>
            cb({ localSecrets: { apiToken: 'test-token' } })
          ),
        },
      },
    })
    vi.stubGlobal('fetch', mockFetch)

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        url: '',
        collection: '',
        chunks_ingested: 0,
        processing_time_ms: 0,
        title: null,
        warning: null,
      }),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    await apiClient.ingestUrl('https://example.com')

    const headers = mockFetch.mock.calls[0][1].headers as Record<string, string>
    expect(headers['X-Extension-Token']).toBe('test-token')
  })

  it('passes abort signal', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        url: '',
        collection: '',
        chunks_ingested: 0,
        processing_time_ms: 0,
        title: null,
        warning: null,
      }),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    const ctrl = new AbortController()
    await apiClient.ingestUrl('https://example.com', ctrl.signal)

    expect(mockFetch.mock.calls[0][1].signal).toBe(ctrl.signal)
  })
})
