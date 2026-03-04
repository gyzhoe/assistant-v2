import type { ExtensionMessage } from '../shared/messages'
import { STORAGE_KEY_SECRETS, NATIVE_HOST, debugLog } from '../shared/constants'

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
    const msg = message

    if (
      msg.type === 'TICKET_DATA_UPDATED' ||
      msg.type === 'INSERT_SUCCESS' ||
      msg.type === 'INSERT_FAILED' ||
      msg.type === 'NOT_A_TICKET_PAGE'
    ) {
      // Only re-broadcast when the sender is a content script (has a tab).
      // If the sender is the sidebar, it already received the message — don't
      // re-broadcast or we create a duplicate delivery loop.
      if (sender.tab) {
        chrome.runtime.sendMessage(msg).catch(() => {
          // Sidebar may not be open yet — ignore
        })
      }
      sendResponse({ ok: true })
      return true
    }

    if (msg.type === 'INSERT_REPLY' || msg.type === 'REQUEST_TICKET_DATA') {
      // Forward from sidebar → active tab's content script.
      // Use lastFocusedWindow for better multi-window targeting.
      chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs) => {
        const activeTab = tabs[0]
        if (activeTab?.id !== undefined) {
          chrome.tabs.sendMessage(activeTab.id, msg)
            .then(() => sendResponse({ ok: true }))
            .catch(() => sendResponse({ ok: false, reason: 'content script unreachable' }))
        } else {
          sendResponse({ ok: false, reason: 'no active tab' })
        }
      })
      return true
    }

    return false
  }
)

/**
 * Auto-provision API token on first install.
 * Reads the token from the backend .env via native messaging
 * and stores it in chrome.storage.local so the extension is
 * authenticated from the start — zero user configuration.
 */
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason !== 'install' && details.reason !== 'update') return

  chrome.runtime.sendNativeMessage(NATIVE_HOST, { action: 'get_token' }, (response) => {
    if (chrome.runtime.lastError) {
      debugLog('Auto-token: native host unavailable:', chrome.runtime.lastError.message)
      return
    }
    if (response?.ok && response.token) {
      chrome.storage.local.set({ [STORAGE_KEY_SECRETS]: { apiToken: response.token } }, () => {
        debugLog('Auto-token: API token provisioned from backend .env')
      })
    } else {
      debugLog('Auto-token: no token available:', response?.error ?? 'unknown')
    }
  })
})
