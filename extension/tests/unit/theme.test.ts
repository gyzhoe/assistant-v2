import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

// Capture matchMedia listeners so we can simulate OS theme changes
let mediaListeners: Array<() => void> = []
let mediaMatches = false

function createMockMatchMedia() {
  return vi.fn().mockImplementation((query: string) => ({
    // Use getter so mq.matches reflects current mediaMatches value
    get matches() { return query === '(prefers-color-scheme: dark)' ? mediaMatches : false },
    media: query,
    addEventListener: vi.fn((_e: string, cb: () => void) => { mediaListeners.push(cb) }),
    removeEventListener: vi.fn((_e: string, cb: () => void) => {
      mediaListeners = mediaListeners.filter((l) => l !== cb)
    }),
  }))
}

// Mock chrome storage — storedSettings is returned by sync.get
let storedSettings: Record<string, unknown> = {}

vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb(storedSettings)),
      set: vi.fn((data: Record<string, unknown>, cb?: () => void) => {
        Object.assign(storedSettings, data)
        cb?.()
      }),
    },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
  runtime: {
    sendMessage: vi.fn(),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
    lastError: null,
  },
})

// Stub scrollIntoView for jsdom
Element.prototype.scrollIntoView = vi.fn()

describe('useTheme hook', () => {
  beforeEach(() => {
    mediaMatches = false
    mediaListeners = []
    storedSettings = {}
    vi.stubGlobal('matchMedia', createMockMatchMedia())
    vi.resetModules()
  })

  it('resolves to "light" when settings.theme = "system" and OS is light', async () => {
    mediaMatches = false
    const { useTheme } = await import('../../src/sidebar/hooks/useTheme')
    const { result } = renderHook(() => useTheme())

    // Wait for useSettings to load from chrome.storage (async)
    await waitFor(() => {
      expect(result.current.themeSetting).toBe('system')
    })
    expect(result.current.resolvedTheme).toBe('light')
  })

  it('resolves to "dark" when settings.theme = "dark"', async () => {
    storedSettings = { appSettings: { theme: 'dark' } }
    const { useTheme } = await import('../../src/sidebar/hooks/useTheme')
    const { result } = renderHook(() => useTheme())

    await waitFor(() => {
      expect(result.current.resolvedTheme).toBe('dark')
    })
  })

  it('resolves to "light" when settings.theme = "light"', async () => {
    storedSettings = { appSettings: { theme: 'light' } }
    const { useTheme } = await import('../../src/sidebar/hooks/useTheme')
    const { result } = renderHook(() => useTheme())

    await waitFor(() => {
      expect(result.current.resolvedTheme).toBe('light')
    })
  })

  it('cycleTheme cycles system -> light -> dark -> system', async () => {
    const { useTheme } = await import('../../src/sidebar/hooks/useTheme')
    const { result } = renderHook(() => useTheme())

    await waitFor(() => {
      expect(result.current.themeSetting).toBe('system')
    })

    await act(async () => { result.current.cycleTheme() })
    expect(result.current.themeSetting).toBe('light')

    await act(async () => { result.current.cycleTheme() })
    expect(result.current.themeSetting).toBe('dark')

    await act(async () => { result.current.cycleTheme() })
    expect(result.current.themeSetting).toBe('system')
  })

  it('updates resolvedTheme when matchMedia changes in system mode', async () => {
    mediaMatches = false
    const { useTheme } = await import('../../src/sidebar/hooks/useTheme')
    const { result } = renderHook(() => useTheme())

    await waitFor(() => {
      expect(result.current.resolvedTheme).toBe('light')
    })

    // Simulate OS switching to dark
    mediaMatches = true
    act(() => {
      mediaListeners.forEach((fn) => fn())
    })

    expect(result.current.resolvedTheme).toBe('dark')
  })
})
