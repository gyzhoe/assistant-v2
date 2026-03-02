import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'

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

// Mutable health mock — allows toggling online/offline
let healthOnline = false
const mockHealth = vi.fn().mockImplementation(() => {
  if (healthOnline) {
    return Promise.resolve({ status: 'ok', version: '1.0.0', ollama_reachable: false, chroma_doc_counts: {} })
  }
  return Promise.reject(new Error('Connection refused'))
})

vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    health: (...args: unknown[]) => mockHealth(...args),
    shutdown: vi.fn().mockResolvedValue(undefined),
    ollamaStop: vi.fn().mockResolvedValue({}),
    ollamaStart: vi.fn().mockResolvedValue({}),
    models: vi.fn().mockResolvedValue([]),
  },
  sendNativeCommand: vi.fn().mockResolvedValue({ ok: false }),
}))

import { useSidebarStore } from '../../src/sidebar/store/sidebarStore'

describe('BackendControl — health poll backoff', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    document.body.innerHTML = ''
    healthOnline = false
    useSidebarStore.setState({
      ticketData: null,
      isTicketPage: false,
      selectedModel: 'qwen2.5:14b',
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function renderBackendControl() {
    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { BackendControl } = await import('../../src/sidebar/components/BackendControl')

    const result = render(
      React.createElement(BackendControl, {
        themeSetting: 'system' as const,
        resolvedTheme: 'light' as const,
        onCycleTheme: () => {},
      }),
    )

    // Allow initial health check to run
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    return result
  }

  it('polls at base 5s interval when online', async () => {
    healthOnline = true
    await renderBackendControl()

    const callsBefore = mockHealth.mock.calls.length

    // Advance one base poll cycle
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(mockHealth.mock.calls.length).toBeGreaterThan(callsBefore)
  })

  it('applies exponential backoff when offline: 5s → 15s → 30s → 60s', async () => {
    healthOnline = false
    await renderBackendControl()

    const timestamps: number[] = []
    let elapsedMs = 100 // account for initial check advance

    // Record call times by watching mock call counts
    const countAfterInitial = mockHealth.mock.calls.length

    // 1st backoff step: should fire at base 5s
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    elapsedMs += 5000
    const afterFirst = mockHealth.mock.calls.length
    timestamps.push(afterFirst - countAfterInitial)

    // 2nd backoff step: should fire at 15s
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
    elapsedMs += 15000
    const afterSecond = mockHealth.mock.calls.length
    timestamps.push(afterSecond - afterFirst)

    // 3rd backoff step: should fire at 30s
    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
    elapsedMs += 30000
    const afterThird = mockHealth.mock.calls.length
    timestamps.push(afterThird - afterSecond)

    // Each step should have exactly 1 call
    expect(timestamps[0]).toBe(1)
    expect(timestamps[1]).toBe(1)
    expect(timestamps[2]).toBe(1)
  })

  it('resets backoff to 5s on reconnect', async () => {
    healthOnline = false
    await renderBackendControl()

    // Skip through offline backoff cycles
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })

    // Now come back online
    healthOnline = true
    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })

    const callsAfterReconnect = mockHealth.mock.calls.length

    // Should now poll at base 5s interval
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(mockHealth.mock.calls.length).toBe(callsAfterReconnect + 1)

    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(mockHealth.mock.calls.length).toBe(callsAfterReconnect + 2)
  })
})
