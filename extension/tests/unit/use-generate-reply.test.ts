import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
  runtime: {
    sendMessage: vi.fn().mockResolvedValue(undefined),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
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

const mockGenerate = vi.fn()
vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    generate: (...args: unknown[]) => mockGenerate(...args),
    models: vi.fn().mockResolvedValue(['qwen2.5:14b']),
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

const ticketData = {
  subject: 'VPN issue',
  description: 'Cannot connect to VPN',
  requesterName: 'Alice',
  category: 'Network',
  status: 'Open',
  ticketUrl: 'http://helpdesk.local/ticket/1',
  customFields: {},
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
      selectedModel: 'qwen2.5:14b',
      isInserted: false,
      isEditingReply: false,
      replyRating: null,
      pinnedArticles: [],
      settings: {
        backendUrl: 'http://localhost:8765',
        defaultModel: 'qwen2.5:14b',
        availableModels: ['qwen2.5:14b'],
        selectorOverrides: {},
        promptSuffix: '',
        theme: 'system',
      },
      settingsLoading: false,
    })
  })

  it('sets isGenerating to true during generation', async () => {
    let resolveGenerate: (v: unknown) => void
    mockGenerate.mockImplementation(() => new Promise((resolve) => { resolveGenerate = resolve }))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    // Start generation (don't await)
    let generatePromise: Promise<void>
    act(() => {
      generatePromise = result.current.generate()
    })

    expect(useSidebarStore.getState().isGenerating).toBe(true)

    // Resolve to clean up
    await act(async () => {
      resolveGenerate!({ reply: 'done', model_used: 'qwen2.5:14b', context_docs: [], latency_ms: 100 })
      await generatePromise!
    })
  })

  it('sends correct payload fields in API call', async () => {
    mockGenerate.mockResolvedValueOnce({ reply: 'Hi', model_used: 'qwen2.5:14b', context_docs: [], latency_ms: 50 })

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(mockGenerate).toHaveBeenCalledWith(
      expect.objectContaining({
        ticket_subject: 'VPN issue',
        ticket_description: 'Cannot connect to VPN',
        requester_name: 'Alice',
        category: 'Network',
        status: 'Open',
        model: 'qwen2.5:14b',
        include_web_context: true,
      }),
      expect.any(AbortSignal),
    )
  })

  it('sets reply text on successful generation', async () => {
    mockGenerate.mockResolvedValueOnce({ reply: 'Try restarting.', model_used: 'qwen2.5:14b', context_docs: [], latency_ms: 50 })

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(useSidebarStore.getState().reply).toBe('Try restarting.')
  })

  it('classifies OLLAMA_DOWN on 503 error', async () => {
    const { ApiError } = await import('../../src/lib/api-client')
    mockGenerate.mockRejectedValueOnce(new ApiError(503, { error_code: 'OLLAMA_DOWN' }))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(useSidebarStore.getState().generateError).toBe('Ollama is not running. Please start it and try again.')
  })

  it('classifies network TypeError as connection error', async () => {
    mockGenerate.mockRejectedValueOnce(new TypeError('Failed to fetch'))

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
    mockGenerate.mockRejectedValueOnce(abortError)

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    // AbortError should NOT set an error message
    expect(useSidebarStore.getState().generateError).toBeNull()
  })

  it('resets isGenerating in finally block after error', async () => {
    mockGenerate.mockRejectedValueOnce(new Error('Something broke'))

    const { renderHook, act } = await import('@testing-library/react')
    const { useGenerateReply } = await import('../../src/sidebar/hooks/useGenerateReply')
    const { result } = renderHook(() => useGenerateReply())

    await act(async () => {
      await result.current.generate()
    })

    expect(useSidebarStore.getState().isGenerating).toBe(false)
    expect(useSidebarStore.getState().generateError).toBe('Something broke')
  })
})
