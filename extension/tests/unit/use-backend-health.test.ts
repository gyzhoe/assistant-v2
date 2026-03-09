import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'
import { renderHook } from '@testing-library/react'

// --- Mock chrome APIs ---
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: {
      get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})),
      set: vi.fn(),
    },
  },
  runtime: {
    sendMessage: vi.fn().mockResolvedValue(undefined),
    sendNativeMessage: vi.fn(),
    openOptionsPage: vi.fn(),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
  },
})

vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))
Element.prototype.scrollIntoView = vi.fn()

// --- Mock api-client module ---
const mockHealth = vi.fn()

vi.mock('../../src/lib/cors-detect', () => ({
  isCorsProbablyBlocked: vi.fn().mockResolvedValue(false),
}))

vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    health: (...args: unknown[]) => mockHealth(...args),
    shutdown: vi.fn().mockResolvedValue(undefined),
    llmStop: vi.fn().mockResolvedValue({}),
    llmStart: vi.fn().mockResolvedValue({}),
    llmRestart: vi.fn().mockResolvedValue({}),
    models: vi.fn().mockResolvedValue({ models: [], current: '' }),
  },
  sendNativeCommand: vi.fn().mockResolvedValue({ ok: false }),
}))

import { useSidebarStore } from '../../src/sidebar/store/sidebarStore'
import { useBackendHealth } from '../../src/sidebar/hooks/useBackendHealth'

describe('useBackendHealth', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    useSidebarStore.setState({
      llmReachable: false,
      chromaDocCounts: {},
      modelConfirmed: false,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with checking status', () => {
    mockHealth.mockResolvedValue({
      status: 'ok',
      version: '2.1.0',
      llm_reachable: true,
      chroma_doc_counts: {},
    })

    const { result } = renderHook(() => useBackendHealth())

    // Before the initial health check resolves, status should be checking
    expect(result.current.status).toBe('checking')
    expect(result.current.version).toBe('')
    expect(result.current.llmOk).toBe(false)
  })

  it('updates to online after successful health check', async () => {
    mockHealth.mockResolvedValue({
      status: 'ok',
      version: '2.1.0',
      llm_reachable: true,
      chroma_doc_counts: { whd_tickets: 100 },
    })

    const { result } = renderHook(() => useBackendHealth())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    expect(result.current.status).toBe('online')
    expect(result.current.version).toBe('2.1.0')
    expect(result.current.llmOk).toBe(true)
    expect(useSidebarStore.getState().llmReachable).toBe(true)
    expect(useSidebarStore.getState().chromaDocCounts).toEqual({ whd_tickets: 100 })
  })

  it('sets offline status when health check fails', async () => {
    mockHealth.mockRejectedValue(new Error('Connection refused'))

    const { result } = renderHook(() => useBackendHealth())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    expect(result.current.status).toBe('offline')
    expect(result.current.llmOk).toBe(false)
    expect(result.current.version).toBe('')
    expect(useSidebarStore.getState().llmReachable).toBe(false)
  })

  it('polls at base 5s interval when online', async () => {
    mockHealth.mockResolvedValue({
      status: 'ok',
      version: '2.1.0',
      llm_reachable: true,
      chroma_doc_counts: {},
    })

    renderHook(() => useBackendHealth())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const callsAfterInitial = mockHealth.mock.calls.length

    // Advance one poll cycle
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(mockHealth.mock.calls.length).toBeGreaterThan(callsAfterInitial)
  })

  it('cleans up timer on unmount', async () => {
    mockHealth.mockResolvedValue({
      status: 'ok',
      version: '2.1.0',
      llm_reachable: true,
      chroma_doc_counts: {},
    })

    const { result, unmount } = renderHook(() => useBackendHealth())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    expect(result.current.status).toBe('online')

    const callsBeforeUnmount = mockHealth.mock.calls.length
    unmount()

    // Advance past several poll cycles - no new calls should happen
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000)
    })

    expect(mockHealth.mock.calls.length).toBe(callsBeforeUnmount)
  })

  it('pauses polling when document becomes hidden and resumes on visible', async () => {
    mockHealth.mockResolvedValue({
      status: 'ok',
      version: '2.1.0',
      llm_reachable: true,
      chroma_doc_counts: {},
    })

    renderHook(() => useBackendHealth())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    const callsBefore = mockHealth.mock.calls.length

    // Simulate tab going hidden
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', writable: true, configurable: true })
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    // Advance well past a normal poll cycle - no new calls should happen
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000)
    })
    expect(mockHealth.mock.calls.length).toBe(callsBefore)

    // Restore visibility
    Object.defineProperty(document, 'visibilityState', { value: 'visible', writable: true, configurable: true })
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      await vi.advanceTimersByTimeAsync(100)
    })

    // Should have polled immediately on becoming visible
    expect(mockHealth.mock.calls.length).toBeGreaterThan(callsBefore)
  })
})
