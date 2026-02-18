import { DOMReader } from './dom-reader'
import { SidebarHost } from './sidebar-host'
import type { SidebarToContentMessage } from '../shared/messages'
import type { DOMInserter } from './dom-inserter'

let inserter: DOMInserter | null = null

async function init(): Promise<void> {
  const { DOMInserter: DOMInserterClass } = await import('./dom-inserter')
  const { SidebarHost: SidebarHostClass } = await import('./sidebar-host')

  const reader = new DOMReader()
  inserter = new DOMInserterClass()
  const host = new SidebarHostClass(reader)
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
      const reader = new DOMReader()
      const data = reader.extract()
      if (data) {
        chrome.runtime.sendMessage({ type: 'TICKET_DATA_UPDATED', payload: data }).catch(() => {})
      }
      sendResponse({ ok: true })
      return true
    }

    return false
  }
)

init().catch(console.error)
