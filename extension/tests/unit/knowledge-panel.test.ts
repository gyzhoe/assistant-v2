import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
  runtime: {
    sendMessage: vi.fn().mockResolvedValue(undefined),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
  },
})

// Stub scrollIntoView for jsdom
Element.prototype.scrollIntoView = vi.fn()

// Mock matchMedia for any theme-dependent code
vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))

// Mock apiClient
vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    health: vi.fn().mockResolvedValue({
      status: 'ok',
      ollama_reachable: true,
      chroma_ready: true,
      chroma_doc_counts: { whd_tickets: 10, kb_articles: 5 },
      version: '1.3.0',
    }),
    clearCollection: vi.fn().mockResolvedValue(undefined),
    uploadFile: vi.fn().mockResolvedValue({
      filename: 'test.pdf',
      collection: 'kb_articles',
      chunks_ingested: 3,
      processing_time_ms: 100,
      warning: null,
    }),
  },
  ApiError: class ApiError extends Error {
    constructor(public readonly status: number, public readonly body: unknown) {
      super(`API error ${status}`)
    }
  },
}))

// Mock crypto.randomUUID
let uuidCounter = 0
vi.stubGlobal('crypto', {
  randomUUID: () => `uuid-${++uuidCounter}`,
})

describe('KnowledgePanel', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    uuidCounter = 0
    vi.clearAllMocks()
  })

  it('renders collapsed by default', async () => {
    const React = await import('react')
    const { render, screen } = await import('@testing-library/react')
    const { KnowledgePanel } = await import('../../src/sidebar/components/KnowledgePanel')

    render(React.createElement(KnowledgePanel))

    const trigger = screen.getByRole('button', { name: /knowledge base/i })
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(document.getElementById('kb-panel-body')).toBeNull()
  })

  it('expands on click', async () => {
    const React = await import('react')
    const { render, screen, fireEvent } = await import('@testing-library/react')
    const { KnowledgePanel } = await import('../../src/sidebar/components/KnowledgePanel')

    render(React.createElement(KnowledgePanel))

    const trigger = screen.getByRole('button', { name: /knowledge base/i })
    fireEvent.click(trigger)

    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(document.getElementById('kb-panel-body')).not.toBeNull()
  })

  it('shows Import and Manage tabs when expanded', async () => {
    const React = await import('react')
    const { render, screen, fireEvent } = await import('@testing-library/react')
    const { KnowledgePanel } = await import('../../src/sidebar/components/KnowledgePanel')

    render(React.createElement(KnowledgePanel))

    fireEvent.click(screen.getByRole('button', { name: /knowledge base/i }))

    expect(screen.getByRole('tab', { name: /import/i })).toBeTruthy()
    expect(screen.getByRole('tab', { name: /manage/i })).toBeTruthy()
  })

  it('Import tab is active by default', async () => {
    const React = await import('react')
    const { render, screen, fireEvent } = await import('@testing-library/react')
    const { KnowledgePanel } = await import('../../src/sidebar/components/KnowledgePanel')

    render(React.createElement(KnowledgePanel))

    fireEvent.click(screen.getByRole('button', { name: /knowledge base/i }))

    const importTab = screen.getByRole('tab', { name: /import/i })
    expect(importTab.getAttribute('aria-selected')).toBe('true')

    const manageTab = screen.getByRole('tab', { name: /manage/i })
    expect(manageTab.getAttribute('aria-selected')).toBe('false')
  })

  it('drop zone renders when expanded', async () => {
    const React = await import('react')
    const { render, screen, fireEvent } = await import('@testing-library/react')
    const { KnowledgePanel } = await import('../../src/sidebar/components/KnowledgePanel')

    render(React.createElement(KnowledgePanel))

    fireEvent.click(screen.getByRole('button', { name: /knowledge base/i }))

    const dropZone = screen.getByRole('button', { name: /drop files/i })
    expect(dropZone).toBeTruthy()
  })
})

describe('KnowledgePanel — store-driven doc counts', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('does not poll health on its own — reads from Zustand store', async () => {
    const { apiClient } = await import('../../src/lib/api-client')
    const mockHealth = apiClient.health as ReturnType<typeof vi.fn>

    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { KnowledgePanel } = await import('../../src/sidebar/components/KnowledgePanel')

    render(React.createElement(KnowledgePanel))

    // KnowledgePanel no longer polls — it reads chromaDocCounts from the store.
    // BackendControl is responsible for fetching health and updating the store.
    expect(mockHealth).not.toHaveBeenCalled()
  })
})
