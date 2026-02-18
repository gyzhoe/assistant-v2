import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome.storage
vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: vi.fn((keys, cb) => cb({})),
    },
    local: {
      get: vi.fn((keys, cb) => cb({})),
    },
  },
})

// Mock fetch
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('apiClient.generate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls /generate with correct body', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        reply: 'Test reply',
        model_used: 'llama3.2:3b',
        context_docs: [],
        latency_ms: 100,
      }),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    const result = await apiClient.generate({
      ticket_subject: 'VPN issue',
      ticket_description: 'Cannot connect',
      requester_name: 'Jane',
      category: 'Network',
      status: 'Open',
      model: 'llama3.2:3b',
      max_context_docs: 5,
      stream: false,
    })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8765/generate',
      expect.objectContaining({ method: 'POST' })
    )
    expect(result.reply).toBe('Test reply')
  })

  it('throws ApiError on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Ollama down', error_code: 'OLLAMA_DOWN' }),
    })

    const { apiClient, ApiError } = await import('../../src/lib/api-client')
    await expect(
      apiClient.generate({
        ticket_subject: 'Test',
        ticket_description: 'Test',
        requester_name: '',
        category: '',
        status: '',
        model: 'llama3.2:3b',
        max_context_docs: 5,
        stream: false,
      })
    ).rejects.toBeInstanceOf(ApiError)
  })
})
