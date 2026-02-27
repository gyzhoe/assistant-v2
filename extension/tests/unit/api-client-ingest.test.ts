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

describe('apiClient.uploadFile', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends FormData to /ingest/upload', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        filename: 'test.pdf',
        collection: 'kb_articles',
        chunks_ingested: 5,
        processing_time_ms: 120,
        warning: null,
      }),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    const result = await apiClient.uploadFile(file)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8765/ingest/upload',
      expect.objectContaining({ method: 'POST' })
    )
    expect(result.filename).toBe('test.pdf')
    expect(result.chunks_ingested).toBe(5)
  })

  it('does NOT set explicit Content-Type header', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        filename: 'test.html',
        collection: 'kb_articles',
        chunks_ingested: 3,
        processing_time_ms: 80,
        warning: null,
      }),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    const file = new File(['<html></html>'], 'test.html', { type: 'text/html' })
    await apiClient.uploadFile(file)

    const callArgs = mockFetch.mock.calls[0][1] as RequestInit
    const headers = callArgs.headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('includes X-Extension-Token header when configured', async () => {
    const chromeLocal = chrome.storage.local.get as ReturnType<typeof vi.fn>
    chromeLocal.mockImplementationOnce((_keys: string, cb: (result: Record<string, unknown>) => void) =>
      cb({ localSecrets: { apiToken: 'my-token' } })
    )

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        filename: 'test.csv',
        collection: 'kb_articles',
        chunks_ingested: 10,
        processing_time_ms: 50,
        warning: null,
      }),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    const file = new File(['a,b'], 'test.csv', { type: 'text/csv' })
    await apiClient.uploadFile(file)

    const callArgs = mockFetch.mock.calls[0][1] as RequestInit
    const headers = callArgs.headers as Record<string, string>
    expect(headers['X-Extension-Token']).toBe('my-token')
  })

  it('throws ApiError on 413, 422, 503', async () => {
    const errorCodes = [413, 422, 503]

    for (const status of errorCodes) {
      vi.clearAllMocks()
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status,
        json: async () => ({ detail: `Error ${status}` }),
      })

      const { apiClient, ApiError } = await import('../../src/lib/api-client')
      const file = new File(['x'], 'test.pdf', { type: 'application/pdf' })
      await expect(apiClient.uploadFile(file)).rejects.toBeInstanceOf(ApiError)
    }
  })
})

describe('apiClient.clearCollection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends POST to /ingest/collections/{name}/clear', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    await apiClient.clearCollection('kb_articles')

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8765/ingest/collections/kb_articles/clear',
      expect.objectContaining({ method: 'POST' })
    )
  })
})
