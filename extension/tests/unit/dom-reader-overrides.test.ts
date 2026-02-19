import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome.storage to serve overrides from appSettings
const storedData: Record<string, unknown> = {}
vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: vi.fn((key: string, cb: (r: Record<string, unknown>) => void) => {
        cb({ [key]: storedData[key] })
      }),
    },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
  runtime: {
    sendMessage: vi.fn(),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
  },
})

// Stub scrollIntoView
Element.prototype.scrollIntoView = vi.fn()

describe('DOMReader loads overrides from appSettings', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    Object.keys(storedData).forEach((k) => delete storedData[k])
  })

  it('reads selectorOverrides from STORAGE_KEY_SETTINGS', async () => {
    // Set up appSettings with selector overrides
    storedData['appSettings'] = {
      selectorOverrides: { subject: '#custom-subject' },
    }

    // Simulate a ticket page
    Object.defineProperty(window, 'location', {
      value: { href: 'http://helpdesk.local/ticketDetail?id=1' },
      writable: true,
    })
    document.body.innerHTML = `
      <form id="ticketDetailForm">
        <input id="custom-subject" value="Override works" />
        <input id="subject" value="Default subject" />
        <textarea id="problemDescription">Desc</textarea>
        <span id="requestorName">Jane</span>
        <select id="categoryName"><option selected>Network</option></select>
        <select id="statusTypeId"><option selected>Open</option></select>
      </form>
    `

    const { DOMReader } = await import('../../src/content/dom-reader')
    const reader = new DOMReader()

    // Wait a tick for the async storage load
    await new Promise((r) => setTimeout(r, 10))

    const ticket = reader.extract()
    expect(ticket).not.toBeNull()
    // The override selector should take priority
    expect(ticket!.subject).toBe('Override works')
  })
})
