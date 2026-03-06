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
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
    onConnect: { addListener: vi.fn(), removeListener: vi.fn() },
  },
})

vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))
Element.prototype.scrollIntoView = vi.fn()

// Mock clipboard API — patch just the clipboard property to avoid breaking navigator
const mockWriteText = vi.fn().mockResolvedValue(undefined)
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: mockWriteText },
  writable: true,
  configurable: true,
})

vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    health: vi.fn().mockResolvedValue({ status: 'ok', version: '1.0.0', llm_reachable: true, chroma_doc_counts: {} }),
    search: vi.fn().mockResolvedValue({ results: [] }),
    feedback: vi.fn().mockResolvedValue({}),
    models: vi.fn().mockResolvedValue(['qwen2.5:14b']),
  },
  sendNativeCommand: vi.fn().mockResolvedValue({ ok: false }),
}))

import { useSidebarStore } from '../../src/sidebar/store/sidebarStore'

describe('ReplyPanel — copy to clipboard', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    document.body.innerHTML = ''
    useSidebarStore.setState({
      reply: 'Hello, this is a test reply.',
      isGenerating: false,
      generateError: null,
      isInserted: false,
      isEditingReply: false,
      replyRating: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function renderReplyPanel() {
    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')
    const result = render(React.createElement(ReplyPanel))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    return result
  }

  it('renders copy button when reply is present', async () => {
    const { container } = await renderReplyPanel()
    const copyBtn = container.querySelector('button[aria-label="Copy reply to clipboard"]') as HTMLButtonElement
    expect(copyBtn).not.toBeNull()
  })

  it('shows clipboard icon by default', async () => {
    const { container } = await renderReplyPanel()
    const copyBtn = container.querySelector('button[aria-label="Copy reply to clipboard"]') as HTMLButtonElement
    // Default state shows SVG icon (not "Copied!")
    expect(copyBtn.textContent?.trim()).not.toContain('Copied!')
    expect(copyBtn.querySelector('svg')).not.toBeNull()
  })

  it('calls clipboard.writeText with reply content', async () => {
    const { container } = await renderReplyPanel()
    const copyBtn = container.querySelector('button[aria-label="Copy reply to clipboard"]') as HTMLButtonElement

    await act(async () => {
      copyBtn.click()
    })

    expect(mockWriteText).toHaveBeenCalledWith('Hello, this is a test reply.')
  })

  it('shows Copied! confirmation after clicking', async () => {
    const { container } = await renderReplyPanel()
    const copyBtn = container.querySelector('button[aria-label="Copy reply to clipboard"]') as HTMLButtonElement

    await act(async () => {
      copyBtn.click()
    })

    // After click, button text should show confirmation
    const updatedBtn = container.querySelector('button[aria-label="Copy reply to clipboard"]') as HTMLButtonElement
    expect(updatedBtn.textContent).toContain('Copied!')
  })

  it('reverts back to icon state after 2.5 seconds', async () => {
    const { container } = await renderReplyPanel()
    const copyBtn = container.querySelector('button[aria-label="Copy reply to clipboard"]') as HTMLButtonElement

    await act(async () => {
      copyBtn.click()
    })

    // Verify "Copied!" is shown
    expect(container.querySelector('button[aria-label="Copy reply to clipboard"]')?.textContent).toContain('Copied!')

    // Advance time past 2.5s
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500)
    })

    // Should revert to icon state
    const updatedBtn = container.querySelector('button[aria-label="Copy reply to clipboard"]') as HTMLButtonElement
    expect(updatedBtn.textContent?.trim()).not.toContain('Copied!')
  })
})
