import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock chrome.runtime
vi.stubGlobal('chrome', {
  runtime: {
    sendMessage: vi.fn().mockResolvedValue(undefined),
  },
})

// We'll import SidebarHost after setting up DOM mocks
describe('SidebarHost', () => {
  let sendMessageMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.useFakeTimers()
    sendMessageMock = chrome.runtime.sendMessage as ReturnType<typeof vi.fn>
    sendMessageMock.mockClear().mockResolvedValue(undefined)
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('start() sends TICKET_DATA_UPDATED when on a ticket page', async () => {
    // Create a mock DOMReader that returns ticket data
    const mockReader = {
      extract: vi.fn().mockReturnValue({
        subject: 'VPN Issue',
        description: 'Cannot connect',
        requesterName: 'Alice',
        category: 'Network',
        status: 'Open',
        ticketUrl: 'http://helpdesk.local/ticket/1',
        customFields: {},
      }),
    }

    const { SidebarHost } = await import('../../src/content/sidebar-host')
    const host = new SidebarHost(mockReader as never)
    host.start()

    expect(sendMessageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'TICKET_DATA_UPDATED' })
    )
  })

  it('start() sends NOT_A_TICKET_PAGE when reader returns null', async () => {
    const mockReader = { extract: vi.fn().mockReturnValue(null) }

    const { SidebarHost } = await import('../../src/content/sidebar-host')
    const host = new SidebarHost(mockReader as never)
    host.start()

    expect(sendMessageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'NOT_A_TICKET_PAGE' })
    )
  })

  it('start() sets up a MutationObserver', async () => {
    const mockReader = { extract: vi.fn().mockReturnValue(null) }

    const { SidebarHost } = await import('../../src/content/sidebar-host')
    const host = new SidebarHost(mockReader as never)

    // Spy on MutationObserver.observe
    const observeSpy = vi.spyOn(MutationObserver.prototype, 'observe')
    host.start()

    expect(observeSpy).toHaveBeenCalled()
    observeSpy.mockRestore()

    host.stop()
  })

  it('re-sends ticket data after debounced DOM mutation', async () => {
    vi.useRealTimers()

    const mockReader = {
      extract: vi.fn()
        .mockReturnValueOnce(null) // initial call from start()
        .mockReturnValue({ // mutation-triggered call
          subject: 'Updated',
          description: 'Updated desc',
          requesterName: 'Bob',
          category: 'Software',
          status: 'Closed',
          ticketUrl: 'http://helpdesk.local/ticket/2',
          customFields: {},
        }),
    }

    const { SidebarHost } = await import('../../src/content/sidebar-host')
    const host = new SidebarHost(mockReader as never)
    host.start()

    expect(mockReader.extract).toHaveBeenCalledTimes(1)

    // Trigger a DOM mutation
    document.body.appendChild(document.createElement('div'))

    // Wait for MutationObserver callback + debounce (300ms + margin)
    await new Promise((r) => setTimeout(r, 450))

    expect(mockReader.extract).toHaveBeenCalledTimes(2)

    host.stop()
  })

  it('stop() disconnects the observer', async () => {
    const mockReader = { extract: vi.fn().mockReturnValue(null) }
    const disconnectSpy = vi.spyOn(MutationObserver.prototype, 'disconnect')

    const { SidebarHost } = await import('../../src/content/sidebar-host')
    const host = new SidebarHost(mockReader as never)
    host.start()
    host.stop()

    expect(disconnectSpy).toHaveBeenCalled()
    disconnectSpy.mockRestore()
  })

  it('stop() clears the debounce timer so no further sends happen', async () => {
    vi.useRealTimers()

    const mockReader = { extract: vi.fn().mockReturnValue(null) }

    const { SidebarHost } = await import('../../src/content/sidebar-host')
    const host = new SidebarHost(mockReader as never)
    host.start()

    // initial sendTicketData call from start()
    expect(mockReader.extract).toHaveBeenCalledTimes(1)

    // Trigger a mutation to start the debounce timer
    document.body.appendChild(document.createElement('span'))

    // Wait for MutationObserver to fire (microtask), but stop before debounce completes
    await new Promise((r) => setTimeout(r, 50))
    host.stop()

    // Wait well past the debounce period (300ms)
    await new Promise((r) => setTimeout(r, 400))

    // extract should NOT have been called again — debounce was cleared
    expect(mockReader.extract).toHaveBeenCalledTimes(1)
  })
})
