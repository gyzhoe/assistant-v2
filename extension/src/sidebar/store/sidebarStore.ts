import { create } from 'zustand'
import { DEFAULT_MODEL } from '../../shared/constants'
import type { TicketData, GenerateResponse } from '../../shared/types'

interface SidebarState {
  ticketData: TicketData | null
  isTicketPage: boolean
  reply: string
  isGenerating: boolean
  generateError: string | null
  lastResponse: GenerateResponse | null
  selectedModel: string
  isInserted: boolean

  setTicketData: (data: TicketData | null) => void
  setIsTicketPage: (val: boolean) => void
  setReply: (reply: string) => void
  setIsGenerating: (val: boolean) => void
  setGenerateError: (err: string | null) => void
  setLastResponse: (resp: GenerateResponse | null) => void
  setSelectedModel: (model: string) => void
  setIsInserted: (val: boolean) => void
  reset: () => void
}

export const useSidebarStore = create<SidebarState>((set) => ({
  ticketData: null,
  isTicketPage: false,
  reply: '',
  isGenerating: false,
  generateError: null,
  lastResponse: null,
  selectedModel: DEFAULT_MODEL,
  isInserted: false,

  setTicketData: (data) => set({ ticketData: data }),
  setIsTicketPage: (val) => set({ isTicketPage: val }),
  setReply: (reply) => set({ reply }),
  setIsGenerating: (val) => set({ isGenerating: val }),
  setGenerateError: (err) => set({ generateError: err }),
  setLastResponse: (resp) => set({ lastResponse: resp }),
  setSelectedModel: (model) => set({ selectedModel: model }),
  setIsInserted: (val) => set({ isInserted: val }),
  reset: () =>
    set({
      reply: '',
      isGenerating: false,
      generateError: null,
      lastResponse: null,
      isInserted: false,
    }),
}))
