import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
const mockGet = vi.fn((keys, callback) => {
  callback({})
})

vi.stubGlobal('chrome', {
  storage: {
    sync: {
      get: mockGet,
    },
  },
  runtime: {
    sendMessage: vi.fn(),
    onMessage: {
      addListener: vi.fn(),
      removeListener: vi.fn(),
    },
  },
})

// We test DOMReader logic via the fixture HTML
describe('DOMReader — isTicketPage', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    // Reset URL
    Object.defineProperty(window, 'location', {
      value: { href: 'http://helpdesk.local/helpdesk/ticketDetail?ticket=123' },
      writable: true,
    })
  })

  it('detects ticket page via URL pattern', async () => {
    const { DOMReader } = await import('../../src/content/dom-reader')
    const reader = new DOMReader()
    expect(reader.isTicketPage()).toBe(true)
  })

  it('detects ticket page via DOM marker', async () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'http://helpdesk.local/other' },
      writable: true,
    })
    document.body.innerHTML = '<form id="ticketDetailForm"></form>'
    const { DOMReader } = await import('../../src/content/dom-reader')
    const reader = new DOMReader()
    expect(reader.isTicketPage()).toBe(true)
  })

  it('returns false on non-ticket page', async () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'http://helpdesk.local/dashboard' },
      writable: true,
    })
    document.body.innerHTML = '<h1>Dashboard</h1>'
    const { DOMReader } = await import('../../src/content/dom-reader')
    const reader = new DOMReader()
    expect(reader.isTicketPage()).toBe(false)
  })
})

describe('DOMReader — extract', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'location', {
      value: { href: 'http://helpdesk.local/ticketDetail?id=42' },
      writable: true,
    })
  })

  it('extracts subject from input#subject', async () => {
    document.body.innerHTML = `
      <input id="subject" value="Cannot login to VPN" />
      <textarea id="problemDescription">User reports VPN login fails.</textarea>
      <span id="requestorName">Alex Johnson</span>
      <select id="categoryName"><option selected>Network</option></select>
      <select id="statusTypeId"><option selected>Open</option></select>
      <textarea id="techNotes"></textarea>
    `
    const { DOMReader } = await import('../../src/content/dom-reader')
    const reader = new DOMReader()
    const data = reader.extract()
    expect(data).not.toBeNull()
    expect(data?.subject).toBe('Cannot login to VPN')
    expect(data?.description).toBe('User reports VPN login fails.')
    expect(data?.requesterName).toBe('Alex Johnson')
  })

  it('returns null on non-ticket page', async () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'http://helpdesk.local/dashboard' },
      writable: true,
    })
    document.body.innerHTML = '<h1>Dashboard</h1>'
    const { DOMReader } = await import('../../src/content/dom-reader')
    const reader = new DOMReader()
    expect(reader.extract()).toBeNull()
  })
})
