import { create } from 'zustand'
import { DEFAULT_MODEL, MAX_PINNED_ARTICLES, STORAGE_KEY_SETTINGS } from '../../shared/constants'
import { DEFAULT_SETTINGS, storage } from '../../lib/storage'
import type { TicketData, GenerateResponse, KBArticlePin, AppSettings } from '../../shared/types'

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
  updateSettings: (updates: Partial<AppSettings>) => Promise<void>
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
