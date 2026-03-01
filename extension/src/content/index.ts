import { DOMReader } from './dom-reader'
import { debugError } from '../shared/constants'
import type { SidebarToContentMessage } from '../shared/messages'
import type { DOMInserter } from './dom-inserter'

let inserter: DOMInserter | null = null
// Cached reader instance — reused across messages instead of re-creating per request
let cachedReader: DOMReader | null = null

async function init(): Promise<void> {
  const { DOMInserter: DOMInserterClass } = await import('./dom-inserter')
  const { SidebarHost: SidebarHostClass } = await import('./sidebar-host')

  cachedReader = new DOMReader()
  await cachedReader.ready()
  inserter = new DOMInserterClass()
  const host = new SidebarHostClass(cachedReader)
  host.start()
}

// Handle messages from sidebar (via background SW)
chrome.runtime.onMessage.addListener(
  (message: SidebarToContentMessage, _sender, sendResponse) => {
    if (message.type === 'INSERT_REPLY') {
      if (inserter) {
        const success = inserter.insertReply(message.payload.text)
        if (success) {
          chrome.runtime.sendMessage({ type: 'INSERT_SUCCESS' }).catch(() => {})
          sendResponse({ ok: true })
        } else {
          chrome.runtime.sendMessage({
            type: 'INSERT_FAILED',
            payload: { reason: 'Reply textarea not found' },
          }).catch(() => {})
          sendResponse({ ok: false })
        }
      }
      return true
    }

    if (message.type === 'REQUEST_TICKET_DATA') {
      const reader = cachedReader ?? new DOMReader()
      reader.ready().then(() => {
        const data = reader.extract()
        if (data) {
          chrome.runtime.sendMessage({ type: 'TICKET_DATA_UPDATED', payload: data }).catch(() => {})
        }
        sendResponse({ ok: true })
      }).catch(() => {
        sendResponse({ ok: false })
      })
      return true
    }

    return false
  }
)

init().catch(debugError)
