import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: vi.fn((_key: string, cb: (result: Record<string, unknown>) => void) => cb({})),
      set: vi.fn((_items: unknown, cb?: () => void) => cb?.()),
    },
    local: {
      get: vi.fn((_k: string, cb: (result: Record<string, unknown>) => void) => cb({})),
      set: vi.fn((_items: unknown, cb?: () => void) => cb?.()),
    },
  },
  runtime: {
    lastError: null,
    sendNativeMessage: vi.fn(),
  },
})

// Mock sendNativeCommand from api-client
const mockSendNativeCommand = vi.fn()
vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    models: vi.fn().mockResolvedValue({ models: [], current: '' }),
  },
  sendNativeCommand: (...args: unknown[]) => mockSendNativeCommand(...args),
}))

// Mock storage
vi.mock('../../src/lib/storage', () => ({
  storage: {
    getSettings: vi.fn().mockResolvedValue({
      backendUrl: 'http://localhost:8765',
      defaultModel: 'qwen2.5:14b',
      promptSuffix: '',
      theme: 'system',
      selectorOverrides: {},
    }),
    saveSettings: vi.fn().mockResolvedValue(undefined),
  },
  DEFAULT_SETTINGS: {
    backendUrl: 'http://localhost:8765',
    defaultModel: 'qwen2.5:14b',
    promptSuffix: '',
    theme: 'system',
    selectorOverrides: {},
  },
}))

import OptionsPage from '../../src/options/OptionsPage'

describe('OptionsPage Auto-detect button', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSendNativeCommand.mockReset()
  })

  it('renders the Auto-detect button', () => {
    render(React.createElement(OptionsPage))
    expect(screen.getByRole('button', { name: /auto-detect/i })).toBeDefined()
  })

  it('calls sendNativeCommand with get_token on click', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: false, error: 'no token' })
    render(React.createElement(OptionsPage))

    fireEvent.click(screen.getByRole('button', { name: /auto-detect/i }))

    await waitFor(() => {
      expect(mockSendNativeCommand).toHaveBeenCalledWith('get_token')
    })
  })

  it('shows success message and fills input on successful detection', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: true, token: 'detected-token-xyz' })
    render(React.createElement(OptionsPage))

    fireEvent.click(screen.getByRole('button', { name: /auto-detect/i }))

    await waitFor(() => {
      expect(screen.getByText(/token detected/i)).toBeDefined()
    })

    const tokenInput = screen.getByPlaceholderText(/paste the api_token/i) as HTMLInputElement
    expect(tokenInput.value).toBe('detected-token-xyz')
  })

  it('shows error message when detection fails', async () => {
    mockSendNativeCommand.mockResolvedValue({ ok: false, error: 'not found' })
    render(React.createElement(OptionsPage))

    fireEvent.click(screen.getByRole('button', { name: /auto-detect/i }))

    await waitFor(() => {
      expect(screen.getByText(/could not detect token/i)).toBeDefined()
    })
  })

  it('shows error message when native command throws', async () => {
    mockSendNativeCommand.mockRejectedValue(new Error('native host error'))
    render(React.createElement(OptionsPage))

    fireEvent.click(screen.getByRole('button', { name: /auto-detect/i }))

    await waitFor(() => {
      expect(screen.getByText(/could not detect token/i)).toBeDefined()
    })
  })

  it('disables button while detecting', async () => {
    let resolvePromise: (value: unknown) => void
    mockSendNativeCommand.mockReturnValue(
      new Promise((resolve) => { resolvePromise = resolve })
    )
    render(React.createElement(OptionsPage))

    const button = screen.getByRole('button', { name: /auto-detect/i }) as HTMLButtonElement
    fireEvent.click(button)

    expect(button.disabled).toBe(true)
    expect(button.textContent).toContain('Detecting')

    resolvePromise!({ ok: true, token: 'abc' })

    await waitFor(() => {
      expect(button.disabled).toBe(false)
    })
  })
})
