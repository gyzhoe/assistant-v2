import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
const addListenerMock = vi.fn()
const removeListenerMock = vi.fn()
const sendMessageMock = vi.fn().mockResolvedValue(undefined)

vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
  runtime: {
    sendMessage: sendMessageMock,
    onMessage: {
      addListener: addListenerMock,
      removeListener: removeListenerMock,
    },
  },
})

// Mock matchMedia (jsdom lacks it)
vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))

// Stub scrollIntoView
Element.prototype.scrollIntoView = vi.fn()

import { useSidebarStore } from '../../src/sidebar/store/sidebarStore'

describe('useTicketData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useSidebarStore.setState({
      ticketData: null,
      isTicketPage: false,
    })
  })

  it('sends REQUEST_TICKET_DATA on mount', async () => {
    const { renderHook } = await import('@testing-library/react')
    const { useTicketData } = await import('../../src/sidebar/hooks/useTicketData')

    renderHook(() => useTicketData())

    expect(sendMessageMock).toHaveBeenCalledWith({ type: 'REQUEST_TICKET_DATA' })
  })

  it('TICKET_DATA_UPDATED message updates store', async () => {
    const { renderHook } = await import('@testing-library/react')
    const { useTicketData } = await import('../../src/sidebar/hooks/useTicketData')

    renderHook(() => useTicketData())

    // Get the listener that was registered
    const listener = addListenerMock.mock.calls[0][0]
    expect(listener).toBeDefined()

    // Simulate receiving a TICKET_DATA_UPDATED message
    const ticketPayload = {
      subject: 'Printer jam',
      description: 'Printer is jammed',
      requesterName: 'Bob',
      category: 'Hardware',
      status: 'Open',
      ticketUrl: 'http://helpdesk.local/ticket/3',
      customFields: {},
      notes: [],
    }

    listener({ type: 'TICKET_DATA_UPDATED', payload: ticketPayload })

    const state = useSidebarStore.getState()
    expect(state.ticketData).toEqual(ticketPayload)
    expect(state.isTicketPage).toBe(true)
  })

  it('cleanup removes chrome.runtime.onMessage listener', async () => {
    const { renderHook } = await import('@testing-library/react')
    const { useTicketData } = await import('../../src/sidebar/hooks/useTicketData')

    const { unmount } = renderHook(() => useTicketData())

    unmount()

    expect(removeListenerMock).toHaveBeenCalled()
  })
})
