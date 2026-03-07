import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome.storage
vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: vi.fn((_keys: unknown, cb: (r: Record<string, unknown>) => void) => cb({})),
    },
    local: {
      get: vi.fn((_keys: unknown, cb: (r: Record<string, unknown>) => void) => cb({})),
    },
  },
})

// Mock fetch
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

/** Helper: create a ReadableStream from SSE text chunks */
function makeSSEBody(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  let index = 0
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]))
        index++
      } else {
        controller.close()
      }
    },
  })
}

const baseRequest = {
  ticket_subject: 'VPN issue',
  ticket_description: 'Cannot connect',
  requester_name: 'Jane',
  category: 'Network',
  status: 'Open',
  model: 'qwen3.5:9b',
  max_context_docs: 5,
  stream: true,
  include_web_context: true,
  prompt_suffix: '',
  custom_fields: {},
}

describe('apiClient.generateStream', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends POST /generate with stream:true and returns async generator', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: makeSSEBody([
        'data: {"type":"token","content":"Hi"}\n\n',
        'data: {"type":"done","latency_ms":100}\n\n',
      ]),
    })

    const { apiClient } = await import('../../src/lib/api-client')
    const stream = await apiClient.generateStream(baseRequest)

    const events = []
    for await (const event of stream) {
      events.push(event)
    }

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8765/generate',
      expect.objectContaining({ method: 'POST' })
    )

    // Verify stream:true was sent in the body
    const body = JSON.parse(mockFetch.mock.calls[0][1].body as string)
    expect(body.stream).toBe(true)

    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({ type: 'token', content: 'Hi' })
    expect(events[1]).toEqual({ type: 'done', latency_ms: 100 })
  })

  it('throws ApiError on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'LLM server down', error_code: 'LLM_DOWN' }),
    })

    const { apiClient, ApiError } = await import('../../src/lib/api-client')
    await expect(apiClient.generateStream(baseRequest)).rejects.toBeInstanceOf(ApiError)
  })

  it('throws ApiError when response body is null', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: null,
    })

    const { apiClient, ApiError } = await import('../../src/lib/api-client')
    await expect(apiClient.generateStream(baseRequest)).rejects.toBeInstanceOf(ApiError)
  })
})
