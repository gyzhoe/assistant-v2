import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome.storage
const storedData: Record<string, unknown> = {}
const mockSyncGet = vi.fn((key, cb) => {
  cb(typeof key === 'string' ? { [key]: storedData[key] } : {})
})
const mockSyncSet = vi.fn((items, cb) => {
  Object.assign(storedData, items)
  cb?.()
})

vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: mockSyncGet,
      set: mockSyncSet,
    },
    local: {
      get: vi.fn((_k, cb) => cb({})),
    },
  },
  runtime: {
    lastError: null,
  },
})

describe('storage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.keys(storedData).forEach((k) => delete storedData[k])
  })

  it('getSettings returns defaults when nothing stored', async () => {
    const { storage, DEFAULT_SETTINGS } = await import('../../src/lib/storage')
    const settings = await storage.getSettings()
    expect(settings).toEqual(DEFAULT_SETTINGS)
  })

  it('getSettings returns stored values merged with defaults', async () => {
    storedData['appSettings'] = { backendUrl: 'http://custom:9000', theme: 'dark' }
    const { storage, DEFAULT_SETTINGS } = await import('../../src/lib/storage')
    const settings = await storage.getSettings()
    expect(settings.backendUrl).toBe('http://custom:9000')
    expect(settings.theme).toBe('dark')
    // Other defaults preserved
    expect(settings.defaultModel).toBe(DEFAULT_SETTINGS.defaultModel)
  })

  it('saveSettings writes to chrome.storage.sync', async () => {
    const { storage, DEFAULT_SETTINGS } = await import('../../src/lib/storage')
    await storage.saveSettings({ ...DEFAULT_SETTINGS, backendUrl: 'http://newhost:8080' })
    expect(mockSyncSet).toHaveBeenCalled()
    const savedArg = mockSyncSet.mock.calls[0][0]
    expect(savedArg['appSettings']).toBeDefined()
    expect(savedArg['appSettings'].backendUrl).toBe('http://newhost:8080')
  })

  it('saveSettings writes directly without reading first (no race)', async () => {
    const { storage, DEFAULT_SETTINGS } = await import('../../src/lib/storage')
    mockSyncGet.mockClear()

    await storage.saveSettings({ ...DEFAULT_SETTINGS, theme: 'dark' })

    // saveSettings should NOT call chrome.storage.sync.get — it writes directly
    expect(mockSyncGet).not.toHaveBeenCalled()
    expect(mockSyncSet).toHaveBeenCalledTimes(1)
    const savedArg = mockSyncSet.mock.calls[0][0]
    expect(savedArg['appSettings'].theme).toBe('dark')
  })
})
