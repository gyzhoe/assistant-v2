import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
const mockGet = vi.fn((_keys, callback) => {
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

  it('extracts fields from WHD table layout via label-based fallback', async () => {
    document.body.innerHTML = `
      <table>
        <tr>
          <td class="labelStandard">Client</td>
          <td class="defaultFont">Hannelore Hendrickx - u0156011</td>
        </tr>
        <tr>
          <td class="labelStandard">Request Type</td>
          <td>
            <select id="ProblemType_123"><option value="0">Account</option><option selected value="14">NEED A PHONE NUMBER</option></select>
          </td>
        </tr>
        <tr>
          <td class="labelStandard">Request Detail</td>
          <td>Please set up a new phone line for the department.</td>
        </tr>
        <tr>
          <td class="labelStandard">Status</td>
          <td><select><option selected>Open</option><option>Closed</option></select></td>
        </tr>
      </table>
    `
    vi.resetModules()
    const { DOMReader } = await import('../../src/content/dom-reader')
    const reader = new DOMReader()
    const data = reader.extract()
    expect(data).not.toBeNull()
    expect(data?.requesterName).toBe('Hannelore Hendrickx - u0156011')
    expect(data?.category).toBe('NEED A PHONE NUMBER')
    expect(data?.description).toBe('Please set up a new phone line for the department.')
    expect(data?.status).toBe('Open')
    // Subject falls back to category when no explicit subject field exists
    expect(data?.subject).toBe('NEED A PHONE NUMBER')
  })
})
