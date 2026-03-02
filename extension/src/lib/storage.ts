import type { AppSettings } from '../shared/types'
import { STORAGE_KEY_SETTINGS, DEFAULT_BACKEND_URL, DEFAULT_MODEL } from '../shared/constants'

export const DEFAULT_SETTINGS: AppSettings = {
  backendUrl: DEFAULT_BACKEND_URL,
  defaultModel: DEFAULT_MODEL,
  availableModels: [DEFAULT_MODEL],
  selectorOverrides: {},
  promptSuffix: '',
  theme: 'system',
  autoInsert: false,
  insertTargetSelector: '',
}

export const storage = {
  async getSettings(): Promise<AppSettings> {
    return new Promise((resolve) => {
      chrome.storage.sync.get(STORAGE_KEY_SETTINGS, (result) => {
        const saved = result[STORAGE_KEY_SETTINGS] as Partial<AppSettings> | undefined
        resolve({ ...DEFAULT_SETTINGS, ...saved })
      })
    })
  },

  async saveSettings(settings: AppSettings): Promise<void> {
    return new Promise((resolve, reject) => {
      chrome.storage.sync.set(
        { [STORAGE_KEY_SETTINGS]: settings },
        () => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message))
          } else {
            resolve()
          }
        }
      )
    })
  },
}
