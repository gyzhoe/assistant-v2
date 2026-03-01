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

describe('useSubmitFeedback toggle', () => {
  beforeEach(() => {
    mockSubmitFeedback.mockReset()
    useSidebarStore.setState(defaultState)
  })

  it('clears rating and skips backend call when same rating clicked twice', async () => {
    mockSubmitFeedback.mockResolvedValue(undefined)
    useSidebarStore.setState({ replyRating: 'good' })

    const { useSubmitFeedback } = await import('../../src/sidebar/hooks/useSubmitFeedback')
    const { renderHook, act } = await import('@testing-library/react')
    const { result } = renderHook(() => useSubmitFeedback())

    await act(async () => {
      await result.current.submitRating('good')
    })

    expect(useSidebarStore.getState().replyRating).toBeNull()
    expect(mockSubmitFeedback).not.toHaveBeenCalled()
  })

  it('switches rating and calls backend when different rating clicked', async () => {
    mockSubmitFeedback.mockResolvedValue(undefined)
    useSidebarStore.setState({ replyRating: 'good' })

    const { useSubmitFeedback } = await import('../../src/sidebar/hooks/useSubmitFeedback')
    const { renderHook, act } = await import('@testing-library/react')
    const { result } = renderHook(() => useSubmitFeedback())

    await act(async () => {
      await result.current.submitRating('bad')
    })

    expect(useSidebarStore.getState().replyRating).toBe('bad')
    expect(mockSubmitFeedback).toHaveBeenCalledOnce()
  })

  it('clears bad rating and skips backend call when thumbs down clicked twice', async () => {
    mockSubmitFeedback.mockResolvedValue(undefined)
    useSidebarStore.setState({ replyRating: 'bad' })

    const { useSubmitFeedback } = await import('../../src/sidebar/hooks/useSubmitFeedback')
    const { renderHook, act } = await import('@testing-library/react')
    const { result } = renderHook(() => useSubmitFeedback())

    await act(async () => {
      await result.current.submitRating('bad')
    })

    expect(useSidebarStore.getState().replyRating).toBeNull()
    expect(mockSubmitFeedback).not.toHaveBeenCalled()
  })
})

describe('useSubmitFeedback rollback', () => {
  beforeEach(() => {
    mockSubmitFeedback.mockReset()
    useSidebarStore.setState(defaultState)
  })

  it('keeps replyRating and sets feedbackError when API call fails', async () => {
    mockSubmitFeedback.mockRejectedValueOnce(new Error('Network error'))

    const { useSubmitFeedback } = await import('../../src/sidebar/hooks/useSubmitFeedback')
    const { renderHook, act, waitFor } = await import('@testing-library/react')
    const { result } = renderHook(() => useSubmitFeedback())

    await act(async () => {
      await result.current.submitRating('good')
    })

    expect(useSidebarStore.getState().replyRating).toBe('good')
    await waitFor(() => {
      expect(result.current.feedbackError).toBe('Rating not saved')
    })
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

  it('keeps buttons enabled after rating is submitted (re-rating allowed)', async () => {
    useSidebarStore.setState({ replyRating: 'good' })

    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')

    const { container } = render(React.createElement(ReplyPanel))
    const thumbsUp = container.querySelector('[aria-label="Rate as helpful"]') as HTMLButtonElement
    const thumbsDown = container.querySelector('[aria-label="Rate as unhelpful"]') as HTMLButtonElement
    expect(thumbsUp.disabled).toBe(false)
    expect(thumbsDown.disabled).toBe(false)
  })

  it('sets aria-pressed on the selected rating button', async () => {
    useSidebarStore.setState({ replyRating: 'bad' })

    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')

    const { container } = render(React.createElement(ReplyPanel))
    const thumbsUp = container.querySelector('[aria-label="Rate as helpful"]') as HTMLButtonElement
    const thumbsDown = container.querySelector('[aria-label="Rate as unhelpful"]') as HTMLButtonElement
    expect(thumbsUp.getAttribute('aria-pressed')).toBe('false')
    expect(thumbsDown.getAttribute('aria-pressed')).toBe('true')
  })

  it('shows success confirmation after successful rating', async () => {
    mockSubmitFeedback.mockResolvedValueOnce(undefined)

    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { fireEvent, waitFor } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')

    const { container } = render(React.createElement(ReplyPanel))
    const thumbsUp = container.querySelector('[aria-label="Rate as helpful"]') as HTMLButtonElement
    fireEvent.click(thumbsUp)

    await waitFor(() => {
      expect(container.querySelector('.rating-saved')).not.toBeNull()
    })
  })

  it('allows re-rating by clicking the other button', async () => {
    mockSubmitFeedback.mockResolvedValue(undefined)

    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { fireEvent, waitFor } = await import('@testing-library/react')
    const { ReplyPanel } = await import('../../src/sidebar/components/ReplyPanel')

    const { container } = render(React.createElement(ReplyPanel))
    const thumbsUp = container.querySelector('[aria-label="Rate as helpful"]') as HTMLButtonElement
    const thumbsDown = container.querySelector('[aria-label="Rate as unhelpful"]') as HTMLButtonElement

    fireEvent.click(thumbsUp)
    await waitFor(() => expect(useSidebarStore.getState().replyRating).toBe('good'))

    fireEvent.click(thumbsDown)
    await waitFor(() => expect(useSidebarStore.getState().replyRating).toBe('bad'))
    expect(thumbsDown.classList.contains('selected')).toBe(true)
    expect(thumbsUp.classList.contains('dimmed')).toBe(true)
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
