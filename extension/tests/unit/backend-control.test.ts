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

// Stub matchMedia (jsdom lacks it)
vi.stubGlobal(
  'matchMedia',
  vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })),
)

// Stub scrollIntoView (jsdom lacks it)
Element.prototype.scrollIntoView = vi.fn()

// --- Mock api-client module ---
const mockShutdown = vi.fn().mockResolvedValue(undefined)
const mockOllamaStop = vi.fn().mockResolvedValue({ status: 'stopped' })
const mockSendNativeCommand = vi.fn()

vi.mock('../../src/lib/cors-detect', () => ({
  isCorsProbablyBlocked: vi.fn().mockResolvedValue(false),
}))

vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    health: vi.fn().mockResolvedValue({
      status: 'ok',
      version: '1.11.0',
      llm_reachable: true,
    }),
    shutdown: (...args: unknown[]) => mockShutdown(...args),
    llmStop: (...args: unknown[]) => mockOllamaStop(...args),
    llmStart: vi.fn().mockResolvedValue({ status: 'started' }),
    models: vi.fn().mockResolvedValue(['qwen3.5:9b']),
  },
  sendNativeCommand: (...args: unknown[]) => mockSendNativeCommand(...args),
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

describe('BackendControl — native stop commands', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    document.body.innerHTML = ''
    // Set store to a state where backend is online
    useSidebarStore.setState({
      ticketData: {
        subject: 'Test',
        description: 'Test',
        requesterName: 'Alice',
        category: 'Network',
        status: 'Open',
        ticketUrl: 'http://test/1',
        customFields: {},
        notes: [],
      },
      isTicketPage: true,
      selectedModel: 'qwen3.5:9b',
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

    // Wait for health check to complete and render service controls
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    return result
  }

  it('stop backend calls sendNativeCommand first', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: true, status: 'stopped', pids: [1234] })

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop backend"]') as HTMLButtonElement
    expect(stopBtn).not.toBeNull()

    await act(async () => {
      stopBtn.click()
    })

    expect(mockSendNativeCommand).toHaveBeenCalledWith('stop_backend')
    // Native succeeded — HTTP shutdown should NOT be called
    expect(mockShutdown).not.toHaveBeenCalled()
  })

  it('stop backend falls back to HTTP when native fails', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: false, error: 'Native messaging unavailable' })
    mockShutdown.mockReturnValue(Promise.resolve())

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop backend"]') as HTMLButtonElement
    expect(stopBtn).not.toBeNull()

    await act(async () => {
      stopBtn.click()
    })

    expect(mockSendNativeCommand).toHaveBeenCalledWith('stop_backend')
    // Native failed — HTTP shutdown should be called as fallback
    expect(mockShutdown).toHaveBeenCalled()
  })

  it('stop LLM server calls sendNativeCommand first', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: true, status: 'stopped' })

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop LLM server"]') as HTMLButtonElement
    expect(stopBtn).not.toBeNull()

    await act(async () => {
      stopBtn.click()
    })

    expect(mockSendNativeCommand).toHaveBeenCalledWith('stop_llm')
    // Native succeeded — HTTP llmStop should NOT be called
    expect(mockOllamaStop).not.toHaveBeenCalled()
  })

  it('stop LLM server falls back to HTTP when native fails', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: false, error: 'not connected' })
    mockOllamaStop.mockResolvedValue({ status: 'stopped' })

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop LLM server"]') as HTMLButtonElement
    expect(stopBtn).not.toBeNull()

    await act(async () => {
      stopBtn.click()
    })

    expect(mockSendNativeCommand).toHaveBeenCalledWith('stop_llm')
    // Native failed — HTTP llmStop should be called as fallback
    expect(mockOllamaStop).toHaveBeenCalled()
  })
})
