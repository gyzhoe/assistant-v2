import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch globally
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Mock sessionStorage
const sessionStore: Record<string, string> = {}
vi.stubGlobal('sessionStorage', {
  getItem: vi.fn((key: string) => sessionStore[key] ?? null),
  setItem: vi.fn((key: string, val: string) => { sessionStore[key] = val }),
  removeItem: vi.fn((key: string) => { delete sessionStore[key] }),
})

function mockOkResponse(body: unknown = {}) {
  return { ok: true, json: async () => body }
}

function mockErrorResponse(status: number, body: unknown = {}) {
  return { ok: false, status, json: async () => body }
}

describe('managementApi', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    // Clear session store between tests
    for (const key of Object.keys(sessionStore)) delete sessionStore[key]
    // Reset module-level token state
    vi.resetModules()
  })

  // ---- setToken / getToken ----

  it('setToken and getToken roundtrip', async () => {
    const { setToken, getToken } = await import('../../src/management/api')
    setToken('my-secret')
    expect(getToken()).toBe('my-secret')
    expect(sessionStorage.setItem).toHaveBeenCalledWith('kb-manage-token', 'my-secret')
  })

  // ---- Token header injection ----

  it('injects X-Extension-Token header on authenticated requests', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ articles: [], total_articles: 0, page: 1, page_size: 20 }))

    const { setToken, managementApi } = await import('../../src/management/api')
    setToken('test-token')
    await managementApi.listArticles({ page: 1, page_size: 20 })

    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers['X-Extension-Token']).toBe('test-token')
  })

  // ---- Health endpoint exempt from token ----

  it('does not send token header on /health endpoint', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ status: 'ok' }))

    const { setToken, managementApi } = await import('../../src/management/api')
    setToken('test-token')
    await managementApi.getHealth()

    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers['X-Extension-Token']).toBeUndefined()
  })

  // ---- Content-Type: application/json ----

  it('sets Content-Type application/json for JSON requests', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ tags: [] }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.getTags()

    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers['Content-Type']).toBe('application/json')
  })

  // ---- FormData skips Content-Type ----

  it('does not set Content-Type header for FormData uploads', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ filename: 'test.pdf', collection: 'kb_articles', chunks_ingested: 5, processing_time_ms: 100, warning: null }))

    const { managementApi } = await import('../../src/management/api')
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    await managementApi.uploadFile(file)

    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers['Content-Type']).toBeUndefined()
  })

  // ---- ApiError on non-ok responses ----

  it('throws ApiError on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce(mockErrorResponse(404, { detail: 'Not found' }))

    const { managementApi, ApiError } = await import('../../src/management/api')
    await expect(managementApi.getStats()).rejects.toBeInstanceOf(ApiError)
  })

  it('ApiError contains status code and body', async () => {
    mockFetch.mockResolvedValueOnce(mockErrorResponse(403, { detail: 'Forbidden' }))

    const { managementApi, ApiError } = await import('../../src/management/api')
    try {
      await managementApi.getStats()
      expect.unreachable('Should have thrown')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      expect((err as InstanceType<typeof ApiError>).status).toBe(403)
    }
  })

  // ---- URL params for listArticles ----

  it('builds URL params for listArticles with search and pagination', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ articles: [], total_articles: 0, page: 2, page_size: 10 }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.listArticles({ page: 2, page_size: 10, search: 'vpn' })

    const url = mockFetch.mock.calls[0][0] as string
    expect(url).toContain('page=2')
    expect(url).toContain('page_size=10')
    expect(url).toContain('search=vpn')
  })

  // ---- encodeURIComponent for article IDs ----

  it('encodes article IDs with special characters', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ article_id: 'a/b', title: 'test', source_type: 'manual', source: '', chunk_count: 1, imported_at: null, chunks: [] }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.getArticle('a/b')

    const url = mockFetch.mock.calls[0][0] as string
    expect(url).toContain(encodeURIComponent('a/b'))
    expect(url).not.toContain('a/b')
  })

  // ---- CRUD: DELETE ----

  it('deleteArticle sends DELETE method', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ article_id: 'abc', chunks_deleted: 3 }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.deleteArticle('abc')

    expect(mockFetch.mock.calls[0][1].method).toBe('DELETE')
  })

  // ---- CRUD: PUT ----

  it('updateArticle sends PUT method with JSON body', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ article_id: 'x', title: 'New', chunks_ingested: 2, processing_time_ms: 50 }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.updateArticle('x', 'New', 'body', ['tag1'])

    const call = mockFetch.mock.calls[0]
    expect(call[1].method).toBe('PUT')
    const body = JSON.parse(call[1].body as string)
    expect(body).toEqual({ title: 'New', content: 'body', tags: ['tag1'] })
  })

  // ---- CRUD: PATCH ----

  it('updateTags sends PATCH method', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ article_id: 'y', tags: ['t1'], chunks_updated: 1 }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.updateTags('y', ['t1'])

    expect(mockFetch.mock.calls[0][1].method).toBe('PATCH')
  })

  // ---- CRUD: POST (createArticle) ----

  it('createArticle sends POST method with JSON body', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ article_id: 'new1', title: 'Test', chunks_ingested: 1, processing_time_ms: 10 }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.createArticle('Test', 'content', ['tag'])

    const call = mockFetch.mock.calls[0]
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body as string)
    expect(body).toEqual({ title: 'Test', content: 'content', tags: ['tag'] })
  })

  // ---- CRUD: POST (ingestUrl) ----

  it('ingestUrl sends POST with url in body', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ url: 'https://example.com', collection: 'kb', chunks_ingested: 3, processing_time_ms: 200, title: 'Example', warning: null }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.ingestUrl('https://example.com')

    const call = mockFetch.mock.calls[0]
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body as string)
    expect(body).toEqual({ url: 'https://example.com' })
  })

  // ---- getToken reads from sessionStorage when module-level is empty ----

  it('getToken falls back to sessionStorage', async () => {
    sessionStore['kb-manage-token'] = 'stored-token'
    const { getToken } = await import('../../src/management/api')
    expect(getToken()).toBe('stored-token')
  })

  // ---- listArticles with source_type filter ----

  it('listArticles includes source_type in URL params when provided', async () => {
    mockFetch.mockResolvedValueOnce(mockOkResponse({ articles: [], total_articles: 0, page: 1, page_size: 20 }))

    const { managementApi } = await import('../../src/management/api')
    await managementApi.listArticles({ page: 1, page_size: 20, source_type: 'pdf' })

    const url = mockFetch.mock.calls[0][0] as string
    expect(url).toContain('source_type=pdf')
  })
})
