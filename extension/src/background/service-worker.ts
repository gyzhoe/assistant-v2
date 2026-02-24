import type { ExtensionMessage, SidebarToContentMessage } from '../shared/messages'

// Open side panel when toolbar button is clicked
chrome.action.onClicked.addListener((tab) => {
  if (tab.id !== undefined) {
    chrome.sidePanel.open({ tabId: tab.id }).catch(() => {
      // Ignore errors (e.g., non-http pages)
    })
  }
})

// Open side panel on keyboard shortcut
chrome.commands.onCommand.addListener((command, tab) => {
  if (command === 'toggle-sidebar' && tab?.id !== undefined) {
    chrome.sidePanel.open({ tabId: tab.id }).catch(() => {
      // Ignore errors
    })
  }
})

/**
 * Message relay hub.
 * Routes messages between content scripts and the sidebar.
 */
chrome.runtime.onMessage.addListener(
  (message: ExtensionMessage, sender, sendResponse: (response?: unknown) => void) => {
    const msg = message as ExtensionMessage

    if (
      msg.type === 'TICKET_DATA_UPDATED' ||
      msg.type === 'INSERT_SUCCESS' ||
      msg.type === 'INSERT_FAILED' ||
      msg.type === 'NOT_A_TICKET_PAGE'
    ) {
      // Forward from content script → sidebar (broadcast to all extension pages)
      chrome.runtime.sendMessage(msg).catch(() => {
        // Sidebar may not be open yet — ignore
      })
      sendResponse({ ok: true })
      return true
    }

    if (msg.type === 'INSERT_REPLY' || msg.type === 'REQUEST_TICKET_DATA') {
      // Forward from sidebar → active tab's content script
      const tabId = sender.tab?.id
      if (tabId !== undefined) {
        chrome.tabs.sendMessage(tabId, msg as SidebarToContentMessage)
          .then(() => sendResponse({ ok: true }))
          .catch(() => sendResponse({ ok: false, reason: 'content script unreachable' }))
      } else {
        // Sender is sidebar — query the active tab
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          const activeTab = tabs[0]
          if (activeTab?.id !== undefined) {
            chrome.tabs.sendMessage(activeTab.id, msg as SidebarToContentMessage)
              .then(() => sendResponse({ ok: true }))
              .catch(() => sendResponse({ ok: false, reason: 'content script unreachable' }))
          } else {
            sendResponse({ ok: false, reason: 'no active tab' })
          }
        })
      }
      return true
    }

    return false
  }
)
