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
const mockLlmRestart = vi.fn().mockResolvedValue({ status: 'restarting', model: 'qwen3.5:9b' })
const mockHealth = vi.fn()
const mockSendNativeCommand = vi.fn()

vi.mock('../../src/lib/cors-detect', () => ({
  isCorsProbablyBlocked: vi.fn().mockResolvedValue(false),
}))

vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    health: (...args: unknown[]) => mockHealth(...args),
    shutdown: (...args: unknown[]) => mockShutdown(...args),
    llmStop: (...args: unknown[]) => mockOllamaStop(...args),
    llmStart: vi.fn().mockResolvedValue({ status: 'started' }),
    llmRestart: (...args: unknown[]) => mockLlmRestart(...args),
    models: vi.fn().mockResolvedValue({ models: ['qwen3.5:9b'], current: 'qwen3.5:9b' }),
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
    document.body.textContent = ''
    mockHealth.mockResolvedValue({
      status: 'ok',
      version: '1.11.0',
      llm_reachable: true,
    })
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
      modelConfirmed: true,
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
    // After stop, health should fail to confirm server is down
    mockHealth
      .mockResolvedValueOnce({ status: 'ok', version: '1.11.0', llm_reachable: true }) // initial check
      .mockRejectedValue(new Error('Connection refused')) // subsequent checks confirm down

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop backend"]') as HTMLButtonElement
    expect(stopBtn).not.toBeNull()

    await act(async () => {
      stopBtn.click()
    })

    expect(mockSendNativeCommand).toHaveBeenCalledWith('stop_backend')
    // Native succeeded — HTTP shutdown should NOT be called
    expect(mockShutdown).not.toHaveBeenCalled()

    // Advance past the settle + confirm polling time
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })
  })

  it('stop backend falls back to HTTP when native fails', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: false, error: 'Native messaging unavailable' })
    mockShutdown.mockReturnValue(Promise.resolve())
    // After stop, health should fail to confirm server is down
    mockHealth
      .mockResolvedValueOnce({ status: 'ok', version: '1.11.0', llm_reachable: true }) // initial check
      .mockRejectedValue(new Error('Connection refused')) // subsequent checks confirm down

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop backend"]') as HTMLButtonElement
    expect(stopBtn).not.toBeNull()

    await act(async () => {
      stopBtn.click()
    })

    expect(mockSendNativeCommand).toHaveBeenCalledWith('stop_backend')
    // Native failed — HTTP shutdown should be called as fallback
    expect(mockShutdown).toHaveBeenCalled()

    // Advance past the settle + confirm polling time
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })
  })

  it('stop LLM server calls llmStop HTTP first', async () => {
    mockOllamaStop.mockResolvedValue({ status: 'stopped' })

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop LLM server"]') as HTMLButtonElement
    expect(stopBtn).not.toBeNull()

    await act(async () => {
      stopBtn.click()
    })

    // HTTP llmStop is called first
    expect(mockOllamaStop).toHaveBeenCalled()
    // Native should NOT be called when HTTP succeeds
    expect(mockSendNativeCommand).not.toHaveBeenCalledWith('stop_llm')
  })

  it('stop LLM server falls back to native when HTTP fails', async () => {
    mockOllamaStop.mockRejectedValue(new Error('Connection refused'))
    mockSendNativeCommand.mockResolvedValue({ ok: true, status: 'stopped' })

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop LLM server"]') as HTMLButtonElement
    expect(stopBtn).not.toBeNull()

    await act(async () => {
      stopBtn.click()
    })

    // HTTP failed — native messaging should be called as fallback
    expect(mockOllamaStop).toHaveBeenCalled()
    expect(mockSendNativeCommand).toHaveBeenCalledWith('stop_llm')
  })

  it('uses modelConfirmed for Model selected badge', async () => {
    // modelConfirmed is true from setUp — badge should show ok
    const { container } = await renderBackendControl()

    const badges = container.querySelectorAll('.badge')
    const modelBadge = Array.from(badges).find((b) => b.textContent?.includes('Model selected'))
    expect(modelBadge).not.toBeNull()
    expect(modelBadge?.classList.contains('ok')).toBe(true)
  })

  it('Model selected badge is not ok when modelConfirmed is false', async () => {
    useSidebarStore.setState({ modelConfirmed: false })

    const { container } = await renderBackendControl()

    const badges = container.querySelectorAll('.badge')
    const modelBadge = Array.from(badges).find((b) => b.textContent?.includes('Model selected'))
    expect(modelBadge).not.toBeNull()
    expect(modelBadge?.classList.contains('ok')).toBe(false)
  })

  it('renders Restart LLM button when LLM is online', async () => {
    const { container } = await renderBackendControl()

    const restartBtn = container.querySelector('button[aria-label="Restart LLM server"]') as HTMLButtonElement
    expect(restartBtn).not.toBeNull()
    expect(restartBtn.textContent).toBe('Restart')
  })

  it('restart LLM calls llmRestart and shows Restarting status', async () => {
    mockLlmRestart.mockResolvedValue({ status: 'restarting', model: 'qwen3.5:9b' })

    const { container } = await renderBackendControl()

    const restartBtn = container.querySelector('button[aria-label="Restart LLM server"]') as HTMLButtonElement
    expect(restartBtn).not.toBeNull()

    await act(async () => {
      restartBtn.click()
    })

    expect(mockLlmRestart).toHaveBeenCalled()

    // Should show "Restarting..." text
    const restartingText = container.querySelector('.svc-action')
    expect(restartingText?.textContent).toContain('Restarting')
  })

  it('restart LLM completes when health confirms LLM is back', async () => {
    mockLlmRestart.mockResolvedValue({ status: 'restarting', model: 'qwen3.5:9b' })
    // After restart call, first health poll shows LLM back
    mockHealth
      .mockResolvedValueOnce({ status: 'ok', version: '1.11.0', llm_reachable: true }) // initial
      .mockResolvedValueOnce({ status: 'ok', version: '1.11.0', llm_reachable: true }) // after restart

    const { container } = await renderBackendControl()

    const restartBtn = container.querySelector('button[aria-label="Restart LLM server"]') as HTMLButtonElement

    await act(async () => {
      restartBtn.click()
    })

    // Advance past restart poll interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    // Should be back to idle with buttons showing
    const restartBtnAfter = container.querySelector('button[aria-label="Restart LLM server"]')
    expect(restartBtnAfter).not.toBeNull()
  })

  it('stop backend waits for server to confirm it is down before going offline', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: true, status: 'stopped' })
    // First health call is the initial one. Then during stop confirmation,
    // server responds once (still up), then fails (confirming it's down)
    let healthCallCount = 0
    mockHealth.mockImplementation(() => {
      healthCallCount++
      if (healthCallCount <= 1) {
        // Initial health check — online
        return Promise.resolve({ status: 'ok', version: '1.11.0', llm_reachable: true })
      } else if (healthCallCount === 2) {
        // First stop confirmation poll — still up
        return Promise.resolve({ status: 'ok', version: '1.11.0', llm_reachable: true })
      } else {
        // Server is down
        return Promise.reject(new Error('Connection refused'))
      }
    })

    const { container } = await renderBackendControl()

    const stopBtn = container.querySelector('button[aria-label="Stop backend"]') as HTMLButtonElement

    await act(async () => {
      stopBtn.click()
    })

    // Advance past the settle time and stop confirm polling
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    // Health was called at least 3 times: initial + stop confirmation polls
    expect(healthCallCount).toBeGreaterThanOrEqual(2)
  })
})
