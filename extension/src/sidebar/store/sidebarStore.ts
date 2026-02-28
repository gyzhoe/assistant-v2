import { create } from 'zustand'
import { DEFAULT_MODEL } from '../../shared/constants'
import type { TicketData, GenerateResponse, KBArticlePin } from '../../shared/types'

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
  pinnedArticles: KBArticlePin[]

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
  pinArticle: (article: KBArticlePin) => void
  unpinArticle: (articleId: string) => void
  cancelGeneration: () => void
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
  pinnedArticles: [],

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
  pinArticle: (article) => {
    const { pinnedArticles } = get()
    if (pinnedArticles.length >= 10) return
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
      pinnedArticles: [],
    })
  },
}))
