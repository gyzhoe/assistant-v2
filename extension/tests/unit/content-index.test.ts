import { describe, it, expect, vi, beforeEach } from 'vitest'

// We test the onMessage listener logic from content/index.ts.
// Since index.ts runs init() on import and uses dynamic imports,
// we mock the dependencies and test the listener behavior directly.

const mockInsertReply = vi.fn()
const mockExtract = vi.fn()
const mockReady = vi.fn().mockResolvedValue(undefined)

// Mock chrome APIs
const onMessageListeners: Array<(
  message: Record<string, unknown>,
  sender: unknown,
  sendResponse: (r: unknown) => void,
) => boolean | void> = []

vi.stubGlobal('chrome', {
  runtime: {
    sendMessage: vi.fn().mockResolvedValue(undefined),
    onMessage: {
      addListener: vi.fn((listener: typeof onMessageListeners[0]) => {
        onMessageListeners.push(listener)
      }),
      removeListener: vi.fn(),
    },
  },
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
})

// Mock the content script dependencies
vi.mock('../../src/content/dom-reader', () => ({
  DOMReader: vi.fn().mockImplementation(() => ({
    ready: mockReady,
    extract: mockExtract,
  })),
}))

vi.mock('../../src/content/dom-inserter', () => ({
  DOMInserter: vi.fn().mockImplementation(() => ({
    insertReply: mockInsertReply,
  })),
}))

vi.mock('../../src/content/sidebar-host', () => ({
  SidebarHost: vi.fn().mockImplementation(() => ({
    start: vi.fn(),
  })),
}))

describe('content/index.ts message handler', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    onMessageListeners.length = 0
    // Reset and re-import the module to trigger init()
    vi.resetModules()

    // Re-apply chrome stubs after resetModules
    vi.stubGlobal('chrome', {
      runtime: {
        sendMessage: vi.fn().mockResolvedValue(undefined),
        onMessage: {
          addListener: vi.fn((listener: typeof onMessageListeners[0]) => {
            onMessageListeners.push(listener)
          }),
          removeListener: vi.fn(),
        },
      },
      storage: {
        sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
      },
    })

    await import('../../src/content/index')
    // Wait for init() to complete
    await new Promise((r) => setTimeout(r, 0))
  })

  it('INSERT_REPLY calls inserter and sends INSERT_SUCCESS', () => {
    mockInsertReply.mockReturnValue(true)

    const listener = onMessageListeners[0]
    expect(listener).toBeDefined()

    const sendResponse = vi.fn()
    listener(
      { type: 'INSERT_REPLY', payload: { text: 'Hello' } },
      {},
      sendResponse,
    )

    expect(mockInsertReply).toHaveBeenCalledWith('Hello')
    expect((chrome.runtime.sendMessage as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'INSERT_SUCCESS' })
    )
    expect(sendResponse).toHaveBeenCalledWith({ ok: true })
  })

  it('INSERT_REPLY sends INSERT_FAILED when inserter returns false', () => {
    mockInsertReply.mockReturnValue(false)

    const listener = onMessageListeners[0]
    const sendResponse = vi.fn()
    listener(
      { type: 'INSERT_REPLY', payload: { text: 'Hello' } },
      {},
      sendResponse,
    )

    expect((chrome.runtime.sendMessage as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'INSERT_FAILED' })
    )
    expect(sendResponse).toHaveBeenCalledWith({ ok: false })
  })

  it('REQUEST_TICKET_DATA calls extract and dispatches data', async () => {
    mockExtract.mockReturnValue({
      subject: 'Test',
      description: 'Desc',
      requesterName: 'Jane',
      category: 'Software',
      status: 'Open',
      ticketUrl: 'http://helpdesk.local/ticket/2',
      customFields: {},
    })

    const listener = onMessageListeners[0]
    const sendResponse = vi.fn()
    listener({ type: 'REQUEST_TICKET_DATA' }, {}, sendResponse)

    // Wait for the async .then chain
    await new Promise((r) => setTimeout(r, 10))

    expect(mockExtract).toHaveBeenCalled()
    expect((chrome.runtime.sendMessage as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'TICKET_DATA_UPDATED' })
    )
  })

  it('unknown message type returns false (not handled)', () => {
    const listener = onMessageListeners[0]
    const sendResponse = vi.fn()
    const result = listener({ type: 'UNKNOWN_TYPE' }, {}, sendResponse)

    expect(result).toBe(false)
    expect(sendResponse).not.toHaveBeenCalled()
  })
})
