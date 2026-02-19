import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
const storedData: Record<string, unknown> = {}
vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: vi.fn((key, cb) => {
        cb(typeof key === 'string' ? { [key]: storedData[key] } : {})
      }),
      set: vi.fn((items, cb) => {
        Object.assign(storedData, items)
        cb?.()
      }),
    },
    local: {
      get: vi.fn((_k, cb) => cb({})),
      set: vi.fn((_items, cb) => cb?.()),
    },
  },
  runtime: { lastError: null },
})

describe('OptionsPage selector overrides', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.keys(storedData).forEach((k) => delete storedData[k])
  })

  it('DEFAULT_SELECTORS has all SelectorConfig keys', async () => {
    const { DEFAULT_SELECTORS } = await import('../../src/shared/constants')
    expect(DEFAULT_SELECTORS.subject).toBe('input#subject')
    expect(DEFAULT_SELECTORS.description).toBe('textarea#problemDescription')
    expect(DEFAULT_SELECTORS.requesterName).toBe('span#requestorName')
    expect(DEFAULT_SELECTORS.category).toBe('select#categoryName option:checked')
    expect(DEFAULT_SELECTORS.status).toBe('select#statusTypeId option:checked')
    expect(DEFAULT_SELECTORS.techNotes).toBe('textarea#techNotes')
  })

  it('storage round-trips selectorOverrides inside appSettings', async () => {
    const { storage } = await import('../../src/lib/storage')
    await storage.saveSettings({
      selectorOverrides: { subject: '#custom-subject', techNotes: '.my-notes textarea' },
    })

    const settings = await storage.getSettings()
    expect(settings.selectorOverrides.subject).toBe('#custom-subject')
    expect(settings.selectorOverrides.techNotes).toBe('.my-notes textarea')
    // Other fields remain undefined (use defaults)
    expect(settings.selectorOverrides.description).toBeUndefined()
  })
})
