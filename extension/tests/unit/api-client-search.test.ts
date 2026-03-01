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

const mockArticleListResponse = {
  articles: [],
  total_articles: 0,
  page: 2,
  page_size: 5,
}

describe('apiClient.searchKBArticles', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockArticleListResponse,
    })
  })

  it('passes search query and page_size to the API', async () => {
    const { apiClient } = await import('../../src/lib/api-client')
    await apiClient.searchKBArticles('vpn issue', 10)

    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain('search=vpn+issue')
    expect(url).toContain('page_size=10')
  })

  it('defaults to page 1 when no page argument given', async () => {
    const { apiClient } = await import('../../src/lib/api-client')
    await apiClient.searchKBArticles('vpn issue')

    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain('page=1')
  })

  it('passes explicit page number to the API', async () => {
    const { apiClient } = await import('../../src/lib/api-client')
    await apiClient.searchKBArticles('vpn issue', 5, 3)

    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toContain('page=3')
  })

  it('passes abort signal', async () => {
    const { apiClient } = await import('../../src/lib/api-client')
    const ctrl = new AbortController()
    await apiClient.searchKBArticles('vpn issue', 5, 1, ctrl.signal)

    expect(mockFetch.mock.calls[0][1].signal).toBe(ctrl.signal)
  })
})
