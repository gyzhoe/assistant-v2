import { create } from 'zustand'
import { DEFAULT_MODEL, MAX_PINNED_ARTICLES, STORAGE_KEY_SETTINGS, STORAGE_KEY_REPLY_CACHE } from '../../shared/constants'
import { DEFAULT_SETTINGS, storage } from '../../lib/storage'
import { debugError } from '../../shared/constants'
import type { TicketData, GenerateResponse, KBArticlePin, AppSettings } from '../../shared/types'

/** Cached reply entry stored in chrome.storage.session */
interface ReplyCacheEntry {
  reply: string
  timestamp: number
}

/** Map of ticket URL → cached reply */
type ReplyCache = Record<string, ReplyCacheEntry>

interface SidebarState {
  ticketData: TicketData | null
  isTicketPage: boolean
  reply: string
  isGenerating: boolean
  generateError: string | null
  lastResponse: GenerateResponse | null
  selectedModel: string
  isInserted: boolean
  abortController: AbortController | null
  isEditingReply: boolean
  replyRating: 'good' | 'bad' | null
  pinnedArticles: KBArticlePin[]
  settings: AppSettings
  settingsLoading: boolean
  ollamaReachable: boolean

  setTicketData: (data: TicketData | null) => void
  setIsTicketPage: (val: boolean) => void
  setReply: (reply: string) => void
  setIsGenerating: (val: boolean) => void
  setGenerateError: (err: string | null) => void
  setLastResponse: (resp: GenerateResponse | null) => void
  setSelectedModel: (model: string) => void
  setIsInserted: (val: boolean) => void
  setAbortController: (ctrl: AbortController | null) => void
  setIsEditingReply: (val: boolean) => void
  setReplyRating: (rating: 'good' | 'bad' | null) => void
  pinArticle: (article: KBArticlePin) => void
  unpinArticle: (articleId: string) => void
  cancelGeneration: () => void
  setOllamaReachable: (val: boolean) => void
  updateSettings: (updates: Partial<AppSettings>) => Promise<void>
  saveReplyForTicket: (ticketUrl: string) => void
  restoreReplyForTicket: (ticketUrl: string) => Promise<void>
  reset: () => void
}

export const useSidebarStore = create<SidebarState>((set, get) => ({
  ticketData: null,
  isTicketPage: false,
  reply: '',
  isGenerating: false,
  generateError: null,
  lastResponse: null,
  selectedModel: DEFAULT_MODEL,
  isInserted: false,
  abortController: null,
  isEditingReply: false,
  replyRating: null,
  pinnedArticles: [],
  settings: DEFAULT_SETTINGS,
  settingsLoading: true,
  ollamaReachable: false,

  setTicketData: (data) => set({ ticketData: data }),
  setIsTicketPage: (val) => set({ isTicketPage: val }),
  setReply: (reply) => set({ reply }),
  setIsGenerating: (val) => set({ isGenerating: val }),
  setGenerateError: (err) => set({ generateError: err }),
  setLastResponse: (resp) => set({ lastResponse: resp }),
  setSelectedModel: (model) => set({ selectedModel: model }),
  setIsInserted: (val) => set({ isInserted: val }),
  setAbortController: (ctrl) => set({ abortController: ctrl }),
  setIsEditingReply: (val) => set({ isEditingReply: val }),
  setReplyRating: (rating) => set({ replyRating: rating }),
  setOllamaReachable: (val) => set({ ollamaReachable: val }),
  pinArticle: (article) => {
    const { pinnedArticles } = get()
    if (pinnedArticles.length >= MAX_PINNED_ARTICLES) return
    if (pinnedArticles.some((a) => a.article_id === article.article_id)) return
    set({ pinnedArticles: [...pinnedArticles, article] })
  },
  unpinArticle: (articleId) => {
    const { pinnedArticles } = get()
    set({ pinnedArticles: pinnedArticles.filter((a) => a.article_id !== articleId) })
  },
  cancelGeneration: () => {
    const { abortController } = get()
    if (abortController) abortController.abort()
    set({ isGenerating: false, abortController: null })
  },
  updateSettings: async (updates) => {
    await storage.saveSettings(updates)
    set((state) => ({ settings: { ...state.settings, ...updates } }))
  },
  saveReplyForTicket: (ticketUrl) => {
    const { reply } = get()
    if (!reply || !ticketUrl) return
    if (typeof chrome === 'undefined' || !chrome.storage?.session) return
    chrome.storage.session.get(STORAGE_KEY_REPLY_CACHE, (result) => {
      const cache = (result[STORAGE_KEY_REPLY_CACHE] as ReplyCache | undefined) ?? {}
      cache[ticketUrl] = { reply, timestamp: Date.now() }
      chrome.storage.session.set({ [STORAGE_KEY_REPLY_CACHE]: cache }, () => {
        if (chrome.runtime.lastError) {
          debugError('Failed to save reply cache:', chrome.runtime.lastError.message)
        }
      })
    })
  },
  restoreReplyForTicket: async (ticketUrl) => {
    if (!ticketUrl) return
    if (typeof chrome === 'undefined' || !chrome.storage?.session) return
    return new Promise<void>((resolve) => {
      chrome.storage.session.get(STORAGE_KEY_REPLY_CACHE, (result) => {
        const cache = (result[STORAGE_KEY_REPLY_CACHE] as ReplyCache | undefined) ?? {}
        const entry = cache[ticketUrl]
        if (entry?.reply) {
          set({ reply: entry.reply, isInserted: false, isEditingReply: false, replyRating: null })
        }
        resolve()
      })
    })
  },
  reset: () => {
    const { abortController } = get()
    if (abortController) abortController.abort()
    set({
      reply: '',
      isGenerating: false,
      generateError: null,
      lastResponse: null,
      isInserted: false,
      abortController: null,
      isEditingReply: false,
      replyRating: null,
      pinnedArticles: [],
    })
  },
}))

// Initialize settings from chrome.storage.sync and listen for changes.
// Guarded for environments where chrome APIs are unavailable (e.g. vitest/jsdom).
if (typeof chrome !== 'undefined' && chrome.storage?.sync) {
  storage.getSettings().then((s) => {
    useSidebarStore.setState({ settings: s, settingsLoading: false })
  })

  if (chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (areaName === 'sync' && changes[STORAGE_KEY_SETTINGS]?.newValue) {
        const saved = changes[STORAGE_KEY_SETTINGS].newValue as Partial<AppSettings>
        useSidebarStore.setState({
          settings: { ...DEFAULT_SETTINGS, ...saved },
          settingsLoading: false,
        })
      }
    })
  }
}
