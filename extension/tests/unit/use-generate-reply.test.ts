import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    session: {
      get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})),
      set: vi.fn((_data: Record<string, unknown>, cb: () => void) => cb()),
    },
  },
  runtime: {
    sendMessage: vi.fn().mockResolvedValue(undefined),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
    lastError: null,
  },
})

// Mock matchMedia (jsdom lacks it)
vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))

// Stub scrollIntoView (jsdom lacks it)
Element.prototype.scrollIntoView = vi.fn()

import type { SSEEvent } from '../../src/shared/types'

const mockGenerateStream = vi.fn()
vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    generate: vi.fn(),
    generateStream: (...args: unknown[]) => mockGenerateStream(...args),
    models: vi.fn().mockResolvedValue({ models: ['qwen3.5:9b'], current: 'qwen3.5:9b' }),
    health: vi.fn().mockResolvedValue({ status: 'ok' }),
  },
  ApiError: class ApiError extends Error {
    status: number
    body: Record<string, unknown>
    constructor(status: number, body: Record<string, unknown> = {}) {
      super(`API error ${status}`)
      this.name = 'ApiError'
      this.status = status
      this.body = body
    }
  },
}))

import { useSidebarStore } from '../../src/sidebar/store/sidebarStore'

/** Helper: create an async generator from SSE events */
async function* mockSSEStream(events: SSEEvent[]): AsyncGenerator<SSEEvent> {
  for (const event of events) {
    yield event
  }
}

const ticketData = {
  subject: 'VPN issue',
  description: 'Cannot connect to VPN',
  requesterName: 'Alice',
  category: 'Network',
  status: 'Open',
  ticketUrl: 'http://helpdesk.local/ticket/1',
  customFields: {},
  notes: [],
}

describe('useGenerateReply', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useSidebarStore.setState({
      ticketData,
      isTicketPage: true,
      reply: '',
      isGenerating: false,
      generateError: null,
      lastResponse: null,
      selectedModel: 'qwen3.5:9b',
      isInserted: false,
      isEditingReply: false,
      replyRating: null,
      pinnedArticles: [],
      settings: {
        backendUrl: 'http://localhost:8765',
        defaultModel: 'qwen3.5:9b',
        availableModels: ['qwen3.5:9b'],
        selectorOverrides: {},
        promptSuffix: '',
        theme: 'system',
        autoInsert: false,
        insertTargetSelector: '',
      },
      settingsLoading: false,
    })
  })

  it('sets isGenerating to true during generation', async () => {
    let resolveStream: () => void
    const waitPromise = new Promise<void>((resolve) => { resolveStream = resolve })
    async function* slowStream(): AsyncGenerator<SSEEvent> {
      await waitPromise
      yield { type: 'done', latency_ms: 100 }
    }
    mockGenerateStream.mockReturnValue(slowStream())

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    let generatePromise: Promise<void>
    act(() => {
      generatePromise = result.current.generate()
    })

    expect(useSidebarStore.getState().isGenerating).toBe(true)

    await act(async () => {
      resolveStream!()
      await generatePromise!
    })
  })

  it('sends correct payload fields in API call', async () => {
    mockGenerateStream.mockReturnValue(mockSSEStream([
      { type: 'meta', context_docs: [] },
      { type: 'token', content: 'Hi' },
      { type: 'done', latency_ms: 50 },
    ]))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(mockGenerateStream).toHaveBeenCalledWith(
      expect.objectContaining({
        ticket_subject: 'VPN issue',
        ticket_description: 'Cannot connect to VPN',
        requester_name: 'Alice',
        category: 'Network',
        status: 'Open',
        model: 'qwen3.5:9b',
        stream: true,
        include_web_context: true,
      }),
      expect.any(AbortSignal),
    )
  })

  it('sets reply from streamed tokens', async () => {
    mockGenerateStream.mockReturnValue(mockSSEStream([
      { type: 'meta', context_docs: [] },
      { type: 'token', content: 'Try ' },
      { type: 'token', content: 'restarting.' },
      { type: 'done', latency_ms: 50 },
    ]))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(useSidebarStore.getState().reply).toBe('Try restarting.')
  })

  it('stores context docs and latency in lastResponse', async () => {
    const docs = [{ content: 'KB article', source: 'kb', score: 0.9, metadata: {} }]
    mockGenerateStream.mockReturnValue(mockSSEStream([
      { type: 'meta', context_docs: docs },
      { type: 'token', content: 'Hello' },
      { type: 'done', latency_ms: 250 },
    ]))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    const resp = useSidebarStore.getState().lastResponse
    expect(resp?.context_docs).toEqual(docs)
    expect(resp?.latency_ms).toBe(250)
    expect(resp?.reply).toBe('Hello')
  })

  it('classifies LLM_DOWN on 503 error', async () => {
    const { ApiError } = await import('../../src/lib/api-client')
    mockGenerateStream.mockImplementation(() => {
      throw new ApiError(503, { error_code: 'LLM_DOWN' })
    })

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    const error = useSidebarStore.getState().generateError
    expect(error).toContain('LLM server is not running')
  })

  it('does not show LLM message for 503 without LLM_DOWN error_code', async () => {
    const { ApiError } = await import('../../src/lib/api-client')
    mockGenerateStream.mockImplementation(() => {
      throw new ApiError(503, { detail: 'Service temporarily unavailable' })
    })

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    const error = useSidebarStore.getState().generateError
    expect(error).not.toContain('Ollama is not running')
    expect(error).toContain('Service temporarily unavailable')
  })

  it('does not show Ollama message for 502 MODEL_ERROR', async () => {
    const { ApiError } = await import('../../src/lib/api-client')
    mockGenerateStream.mockImplementation(() => {
      throw new ApiError(502, { error_code: 'MODEL_ERROR', detail: 'model "foo" not found' })
    })

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    const error = useSidebarStore.getState().generateError
    expect(error).not.toContain('Ollama is not running')
    expect(error).toContain('model "foo" not found')
  })

  it('classifies network TypeError as connection error', async () => {
    mockGenerateStream.mockImplementation(() => {
      throw new TypeError('Failed to fetch')
    })

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(useSidebarStore.getState().generateError).toContain('Network error')
  })

  it('silently handles AbortError (user cancellation)', async () => {
    const abortError = new DOMException('The operation was aborted.', 'AbortError')
    mockGenerateStream.mockImplementation(() => {
      throw abortError
    })

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(useSidebarStore.getState().generateError).toBeNull()
  })

  it('resets isGenerating in finally block after error', async () => {
    mockGenerateStream.mockImplementation(() => {
      throw new Error('Something broke')
    })

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(useSidebarStore.getState().isGenerating).toBe(false)
    expect(useSidebarStore.getState().generateError).toContain('Something broke')
  })

  it('sends INSERT_REPLY when autoInsert is enabled', async () => {
    useSidebarStore.setState({
      settings: {
        ...useSidebarStore.getState().settings,
        autoInsert: true,
      },
    })
    mockGenerateStream.mockReturnValue(mockSSEStream([
      { type: 'meta', context_docs: [] },
      { type: 'token', content: 'Auto-inserted reply' },
      { type: 'done', latency_ms: 50 },
    ]))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(chrome.runtime.sendMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'INSERT_REPLY',
        payload: { text: 'Auto-inserted reply' },
      })
    )
  })

  it('does not send INSERT_REPLY when autoInsert is disabled', async () => {
    mockGenerateStream.mockReturnValue(mockSSEStream([
      { type: 'meta', context_docs: [] },
      { type: 'token', content: 'Normal reply' },
      { type: 'done', latency_ms: 50 },
    ]))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    const insertCalls = vi.mocked(chrome.runtime.sendMessage).mock.calls.filter(
      (call) => (call[0] as { type?: string })?.type === 'INSERT_REPLY'
    )
    expect(insertCalls).toHaveLength(0)
  })

  it('saves reply to session storage after successful generation', async () => {
    mockGenerateStream.mockReturnValue(mockSSEStream([
      { type: 'meta', context_docs: [] },
      { type: 'token', content: 'Cached reply' },
      { type: 'done', latency_ms: 50 },
    ]))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(chrome.storage.session.set).toHaveBeenCalled()
  })

  it('handles SSE error event from stream', async () => {
    mockGenerateStream.mockReturnValue(mockSSEStream([
      { type: 'meta', context_docs: [] },
      { type: 'error', error_code: 'LLM_DOWN', message: 'LLM server is unreachable' },
    ]))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(useSidebarStore.getState().generateError).toContain('LLM server is not running')
  })
})
