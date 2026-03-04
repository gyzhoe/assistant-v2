import { describe, it, expect, vi, beforeEach } from 'vitest'

// Capture listeners registered during module import
type InstalledListener = (details: chrome.runtime.InstalledDetails) => void
const installedListeners: InstalledListener[] = []

// Mock chrome APIs before importing the module
vi.stubGlobal('chrome', {
  action: { onClicked: { addListener: vi.fn() } },
  commands: { onCommand: { addListener: vi.fn() } },
  runtime: {
    onMessage: { addListener: vi.fn() },
    onInstalled: {
      addListener: vi.fn((cb: InstalledListener) => {
        installedListeners.push(cb)
      }),
    },
    sendMessage: vi.fn().mockResolvedValue(undefined),
    sendNativeMessage: vi.fn(),
    lastError: null as { message: string } | null,
  },
  sidePanel: { open: vi.fn().mockResolvedValue(undefined) },
  tabs: {
    query: vi.fn(),
    sendMessage: vi.fn().mockResolvedValue(undefined),
  },
  storage: {
    local: {
      set: vi.fn((_items: unknown, cb?: () => void) => cb?.()),
    },
  },
})

describe('service-worker onInstalled auto-token', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    installedListeners.length = 0
    // Re-apply chrome stub since clearAllMocks may affect it
    vi.mocked(chrome.runtime.onInstalled.addListener).mockImplementation(
      ((cb: InstalledListener) => { installedListeners.push(cb) }) as typeof chrome.runtime.onInstalled.addListener
    )
    Object.defineProperty(chrome.runtime, 'lastError', { value: null, writable: true })
  })

  async function loadServiceWorker() {
    // Reset module registry so the module re-registers listeners
    vi.resetModules()
    await import('../../src/background/service-worker')
  }

  it('registers an onInstalled listener', async () => {
    await loadServiceWorker()
    expect(installedListeners.length).toBeGreaterThan(0)
  })

  it('calls sendNativeMessage with get_token on install', async () => {
    await loadServiceWorker()
    const listener = installedListeners[installedListeners.length - 1]
    listener({ reason: 'install' } as chrome.runtime.InstalledDetails)

    expect(chrome.runtime.sendNativeMessage).toHaveBeenCalledWith(
      'com.assistant.backend_manager',
      { action: 'get_token' },
      expect.any(Function)
    )
  })

  it('stores token on successful response', async () => {
    vi.mocked(chrome.runtime.sendNativeMessage).mockImplementation(
      ((_host: string, _msg: unknown, cb: (response: unknown) => void) => {
        cb({ ok: true, token: 'test-token-abc123' })
      }) as typeof chrome.runtime.sendNativeMessage
    )

    await loadServiceWorker()
    const listener = installedListeners[installedListeners.length - 1]
    listener({ reason: 'install' } as chrome.runtime.InstalledDetails)

    expect(chrome.storage.local.set).toHaveBeenCalledWith(
      { localSecrets: { apiToken: 'test-token-abc123' } },
      expect.any(Function)
    )
  })

  it('re-provisions token on update reason', async () => {
    await loadServiceWorker()
    const listener = installedListeners[installedListeners.length - 1]
    listener({ reason: 'update' } as chrome.runtime.InstalledDetails)

    expect(chrome.runtime.sendNativeMessage).toHaveBeenCalledWith(
      'com.assistant.backend_manager',
      { action: 'get_token' },
      expect.any(Function)
    )
  })

  it('handles native host unavailable gracefully', async () => {
    vi.mocked(chrome.runtime.sendNativeMessage).mockImplementation(
      ((_host: string, _msg: unknown, cb: (response: unknown) => void) => {
        Object.defineProperty(chrome.runtime, 'lastError', {
          value: { message: 'Native host not found' },
          writable: true,
        })
        cb(undefined)
        Object.defineProperty(chrome.runtime, 'lastError', {
          value: null,
          writable: true,
        })
      }) as typeof chrome.runtime.sendNativeMessage
    )

    await loadServiceWorker()
    const listener = installedListeners[installedListeners.length - 1]
    listener({ reason: 'install' } as chrome.runtime.InstalledDetails)

    expect(chrome.storage.local.set).not.toHaveBeenCalled()
  })
})
