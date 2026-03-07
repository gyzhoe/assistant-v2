import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: vi.fn((_key: string, cb: (r: Record<string, unknown>) => void) => cb({})),
      set: vi.fn((_items: Record<string, unknown>, cb?: () => void) => cb?.()),
    },
    local: {
      get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})),
      set: vi.fn((_items: Record<string, unknown>, cb?: () => void) => cb?.()),
      remove: vi.fn((_k: string, cb?: () => void) => cb?.()),
    },
  },
  runtime: {
    lastError: null,
    sendNativeMessage: vi.fn(),
  },
})

vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))

// Mock api-client
const mockModels = vi.fn()
const mockDownloadModels = vi.fn()

vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    models: mockModels,
    downloadModels: mockDownloadModels,
    downloadStatus: vi.fn().mockResolvedValue({
      downloading: true,
      current_model: 'Qwen3-14B-Q4_K_M.gguf',
      bytes_downloaded: 4_100_000_000,
      bytes_total: 9_000_000_000,
      models_completed: 0,
      models_total: 1,
      error: '',
    }),
    cancelDownload: vi.fn().mockResolvedValue({ status: 'cancelling' }),
  },
  sendNativeCommand: vi.fn().mockResolvedValue({ ok: false }),
}))

vi.mock('../../src/lib/storage', () => ({
  storage: {
    getSettings: vi.fn().mockResolvedValue({
      backendUrl: 'http://localhost:8765',
      defaultModel: 'qwen3.5:9b',
      availableModels: [],
      selectorOverrides: {},
      promptSuffix: '',
      theme: 'system',
      autoInsert: false,
      insertTargetSelector: '',
    }),
    saveSettings: vi.fn().mockResolvedValue(undefined),
  },
  DEFAULT_SETTINGS: {
    backendUrl: 'http://localhost:8765',
    defaultModel: 'qwen3.5:9b',
    availableModels: [],
    selectorOverrides: {},
    promptSuffix: '',
    theme: 'system',
    autoInsert: false,
    insertTargetSelector: '',
  },
}))

const MODEL_INFO_RESPONSE = {
  models: ['qwen3.5:9b', 'nomic-embed-text'],
  current: 'qwen3.5:9b',
  model_info: {
    'qwen3.5:9b': { downloaded: true, size_bytes: 5_300_000_000, description: '~5.3 GB', gguf_name: 'Qwen3.5-9B-Q4_K_M.gguf' },
    'qwen3:14b': { downloaded: false, size_bytes: 9_000_000_000, description: '~9 GB', gguf_name: 'Qwen3-14B-Q4_K_M.gguf' },
    'nomic-embed-text': { downloaded: true, size_bytes: 262_000_000, description: '~262 MB', gguf_name: 'nomic-embed-text-v1.5.Q8_0.gguf' },
  },
}

describe('OptionsPage LLM Models section', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
    mockModels.mockResolvedValue(MODEL_INFO_RESPONSE)
    mockDownloadModels.mockResolvedValue({ status: 'started', models: ['qwen3:14b'] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    // Re-stub globals that restoreAllMocks undoes
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
  })

  async function renderOptions(): Promise<HTMLElement> {
    const React = await import('react')
    const { render, act } = await import('@testing-library/react')
    const { default: OptionsPage } = await import('../../src/options/OptionsPage')
    let container!: HTMLElement
    await act(async () => {
      const result = render(React.createElement(OptionsPage))
      container = result.container
    })
    // Let model fetch resolve
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
    return container
  }

  it('renders model list with downloaded and missing models', async () => {
    const container = await renderOptions()

    const cards = container.querySelectorAll('.model-card')
    expect(cards.length).toBe(3)

    const names = Array.from(container.querySelectorAll('.model-card-name'))
    const nameTexts = names.map((n) => n.textContent)
    expect(nameTexts).toContain('qwen3.5:9b')
    expect(nameTexts).toContain('qwen3:14b')
    expect(nameTexts).toContain('nomic-embed-text')

    const downloadedBadges = container.querySelectorAll('.model-status-badge--downloaded')
    expect(downloadedBadges.length).toBe(2)

    const downloadBtn = container.querySelector('.model-status-badge--download')
    expect(downloadBtn).not.toBeNull()
    expect(downloadBtn!.textContent).toBe('Download')
  })

  it('shows Download All Missing button when models are missing', async () => {
    const container = await renderOptions()

    const buttons = Array.from(container.querySelectorAll('button'))
    const downloadAllBtn = buttons.find((b) => b.textContent === 'Download All Missing')
    expect(downloadAllBtn).not.toBeUndefined()
  })

  it('calls downloadModels with model name when per-model Download is clicked', async () => {
    const container = await renderOptions()
    const { act } = await import('@testing-library/react')

    const downloadBtn = container.querySelector('.model-status-badge--download') as HTMLButtonElement
    expect(downloadBtn).not.toBeNull()

    await act(async () => {
      downloadBtn.click()
    })

    expect(mockDownloadModels).toHaveBeenCalledWith(['qwen3:14b'])
  })
})
