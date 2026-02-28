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

// Mock matchMedia for useTheme (jsdom doesn't implement it)
vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))

// Stub scrollIntoView (jsdom doesn't implement it)
Element.prototype.scrollIntoView = vi.fn()

// Mock apiClient at module level so ModelSelector and other components work
const mockSubmitFeedback = vi.fn().mockResolvedValue(undefined)
vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    submitFeedback: mockSubmitFeedback,
    models: vi.fn().mockResolvedValue(['qwen2.5:14b']),
    generate: vi.fn().mockResolvedValue({ reply: 'test', model: 'qwen2.5:14b' }),
    health: vi.fn().mockResolvedValue({ status: 'ok', ollama_reachable: true, chroma_ready: true, chroma_doc_counts: {}, version: '1.0.0' }),
  },
}))

import { useSidebarStore } from '../../src/sidebar/store/sidebarStore'

const defaultState = {
  ticketData: {
    subject: 'VPN not connecting',
    description: 'Cannot connect to VPN',
    requesterName: 'Alice',
    category: 'NETWORK CONNECTION',
    status: 'Open',
    ticketUrl: 'http://helpdesk.local/ticket/1',
    customFields: {},
  },
  isTicketPage: true,
  reply: 'Hi Alice, try clearing your credentials.',
  isGenerating: false,
  generateError: null,
  lastResponse: null,
  selectedModel: 'qwen2.5:14b',
  isInserted: false,
  isEditingReply: false,
  replyRating: null,
}

describe('useSubmitFeedback rollback', () => {
  beforeEach(() => {
    mockSubmitFeedback.mockReset()
    useSidebarStore.setState(defaultState)
  })

  it('rolls back replyRating to null when API call fails', async () => {
    mockSubmitFeedback.mockRejectedValueOnce(new Error('Network error'))

    const { useSubmitFeedback } = await import('../../src/sidebar/hooks/useSubmitFeedback')
    const { renderHook } = await import('@testing-library/react')
    const { result } = renderHook(() => useSubmitFeedback())

    await result.current.submitRating('good')

    expect(useSidebarStore.getState().replyRating).toBeNull()
  })

  it('keeps replyRating when API call succeeds', async () => {
    mockSubmitFeedback.mockResolvedValueOnce(undefined)

    const { useSubmitFeedback } = await import('../../src/sidebar/hooks/useSubmitFeedback')
    const { renderHook } = await import('@testing-library/react')
    const { result } = renderHook(() => useSubmitFeedback())

    await result.current.submitRating('good')

    expect(useSidebarStore.getState().replyRating).toBe('good')
  })
})

describe('ReplyPanel rating buttons', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    mockSubmitFeedback.mockReset().mockResolvedValue(undefined)
    useSidebarStore.setState(defaultState)
  })

  it('shows rating buttons when reply is present', async () => {
    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')

    const { container } = render(React.createElement(ReplyPanel))
    const thumbsUp = container.querySelector('[aria-label="Rate as helpful"]')
    const thumbsDown = container.querySelector('[aria-label="Rate as unhelpful"]')
    expect(thumbsUp).not.toBeNull()
    expect(thumbsDown).not.toBeNull()
  })

  it('disables buttons after rating is submitted', async () => {
    useSidebarStore.setState({ replyRating: 'good' })

    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')

    const { container } = render(React.createElement(ReplyPanel))
    const thumbsUp = container.querySelector('[aria-label="Rate as helpful"]') as HTMLButtonElement
    const thumbsDown = container.querySelector('[aria-label="Rate as unhelpful"]') as HTMLButtonElement
    expect(thumbsUp.disabled).toBe(true)
    expect(thumbsDown.disabled).toBe(true)
  })

  it('applies selected class to chosen rating and dimmed to other', async () => {
    useSidebarStore.setState({ replyRating: 'good' })

    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')

    const { container } = render(React.createElement(ReplyPanel))
    const thumbsUp = container.querySelector('[aria-label="Rate as helpful"]')!
    const thumbsDown = container.querySelector('[aria-label="Rate as unhelpful"]')!
    expect(thumbsUp.classList.contains('selected')).toBe(true)
    expect(thumbsDown.classList.contains('dimmed')).toBe(true)
  })

  it('does not show rating buttons when no reply', async () => {
    useSidebarStore.setState({ reply: '' })

    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')

    const { container } = render(React.createElement(ReplyPanel))
    const thumbsUp = container.querySelector('[aria-label="Rate as helpful"]')
    expect(thumbsUp).toBeNull()
  })
})
