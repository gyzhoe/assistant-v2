import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    session: {
      get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})),
      set: vi.fn((_data: Record<string, unknown>, cb: () => void) => cb()),
    },
    onChanged: { addListener: vi.fn() },
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

const mockModels = vi.fn()
const mockSwitchModel = vi.fn()
const mockHealth = vi.fn()

vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    models: (...args: unknown[]) => mockModels(...args),
    switchModel: (...args: unknown[]) => mockSwitchModel(...args),
    health: (...args: unknown[]) => mockHealth(...args),
    generate: vi.fn(),
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

describe('ModelSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockModels.mockResolvedValue({ models: ['qwen3.5:9b', 'qwen3:14b'], current: 'qwen3.5:9b' })
    mockSwitchModel.mockResolvedValue({ status: 'switching', model: 'qwen3:14b' })
    mockHealth.mockResolvedValue({ status: 'ok', llm_reachable: true, version: '2.0.0' })
    useSidebarStore.setState({
      selectedModel: 'qwen3.5:9b',
      isModelSwitching: false,
      modelConfirmed: false,
      llmReachable: true,
    })
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('fetches models on mount and renders options', async () => {
    const { render, screen, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    const select = screen.getByLabelText('Select LLM model') as HTMLSelectElement
    expect(select).toBeTruthy()
    expect(select.options).toHaveLength(2)
    expect(select.options[0].value).toBe('qwen3.5:9b')
    expect(select.options[1].value).toBe('qwen3:14b')
  })

  it('sets modelConfirmed to true after successful fetchModels', async () => {
    const { render, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    expect(useSidebarStore.getState().modelConfirmed).toBe(true)
  })

  it('sets modelConfirmed to false when fetchModels fails', async () => {
    mockModels.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    const { render, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    expect(useSidebarStore.getState().modelConfirmed).toBe(false)
  })

  it('resets modelConfirmed when LLM goes offline', async () => {
    const { render, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    expect(useSidebarStore.getState().modelConfirmed).toBe(true)

    await act(async () => {
      useSidebarStore.setState({ llmReachable: false })
    })

    expect(useSidebarStore.getState().modelConfirmed).toBe(false)
  })

  it('calls switchModel when user selects a different model', async () => {
    const { render, screen, fireEvent, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    const select = screen.getByLabelText('Select LLM model') as HTMLSelectElement

    await act(async () => {
      fireEvent.change(select, { target: { value: 'qwen3:14b' } })
    })

    expect(mockSwitchModel).toHaveBeenCalledWith('qwen3:14b')
    expect(useSidebarStore.getState().isModelSwitching).toBe(true)
  })

  it('does not call switchModel when selecting the already-current model', async () => {
    const { render, screen, fireEvent, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    const select = screen.getByLabelText('Select LLM model') as HTMLSelectElement

    await act(async () => {
      fireEvent.change(select, { target: { value: 'qwen3.5:9b' } })
    })

    expect(mockSwitchModel).not.toHaveBeenCalled()
    expect(useSidebarStore.getState().isModelSwitching).toBe(false)
  })

  it('disables select during model switching', async () => {
    const { render, screen, fireEvent, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    const select = screen.getByLabelText('Select LLM model') as HTMLSelectElement

    await act(async () => {
      fireEvent.change(select, { target: { value: 'qwen3:14b' } })
    })

    expect(select.disabled).toBe(true)
  })

  it('shows "Switching model..." text during switch', async () => {
    const { render, screen, fireEvent, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Select LLM model'), { target: { value: 'qwen3:14b' } })
    })

    expect(screen.getByText(/Switching model/)).toBeTruthy()
  })

  it('shows "Loading model..." after models endpoint confirms new model', async () => {
    // First call: initial fetch. Second call: poll returns new model.
    mockModels
      .mockResolvedValueOnce({ models: ['qwen3.5:9b', 'qwen3:14b'], current: 'qwen3.5:9b' })
      .mockResolvedValueOnce({ models: ['qwen3.5:9b', 'qwen3:14b'], current: 'qwen3:14b' })
    // Health not ready yet
    mockHealth.mockResolvedValue({ status: 'ok', llm_reachable: false, version: '2.0.0' })

    const { render, screen, fireEvent, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Select LLM model'), { target: { value: 'qwen3:14b' } })
    })

    // Advance past the model poll interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    // Should now show "Loading model..." since models confirms but health is not ready
    expect(screen.getByText(/Loading model/)).toBeTruthy()
    expect(useSidebarStore.getState().isModelSwitching).toBe(true)
  })

  it('completes switch after polling confirms new model AND health is ok', async () => {
    // After switch call, polling returns the new model
    mockModels
      .mockResolvedValueOnce({ models: ['qwen3.5:9b', 'qwen3:14b'], current: 'qwen3.5:9b' }) // initial fetch
      .mockResolvedValueOnce({ models: ['qwen3.5:9b', 'qwen3:14b'], current: 'qwen3:14b' }) // poll response

    // Health confirms LLM is ready
    mockHealth.mockResolvedValue({ status: 'ok', llm_reachable: true, version: '2.0.0' })

    const { render, screen, fireEvent, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Select LLM model'), { target: { value: 'qwen3:14b' } })
    })

    // Advance past the model poll interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    // Advance past the health poll interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    expect(useSidebarStore.getState().isModelSwitching).toBe(false)
    expect(useSidebarStore.getState().selectedModel).toBe('qwen3:14b')
    expect(useSidebarStore.getState().modelConfirmed).toBe(true)
  })

  it('reverts model on switchModel API error', async () => {
    const { ApiError } = await import('../../src/lib/api-client')
    mockSwitchModel.mockRejectedValueOnce(new ApiError(500, { detail: 'Server error' }))

    const { render, screen, fireEvent, act } = await import('@testing-library/react')
    const React = await import('react')
    const { ModelSelector } = await import('../../src/sidebar/components/ModelSelector')

    await act(async () => {
      render(React.createElement(ModelSelector))
    })

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Select LLM model'), { target: { value: 'qwen3:14b' } })
    })

    expect(useSidebarStore.getState().isModelSwitching).toBe(false)
    expect(useSidebarStore.getState().selectedModel).toBe('qwen3.5:9b')
    expect(screen.getByText(/Server error/)).toBeTruthy()
  })
})
