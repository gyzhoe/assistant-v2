import { describe, it, expect, beforeEach } from 'vitest'
import { useSidebarStore } from '../../src/sidebar/store/sidebarStore'

describe('sidebarStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useSidebarStore.setState({
      ticketData: null,
      isTicketPage: false,
      reply: '',
      isGenerating: false,
      generateError: null,
      lastResponse: null,
      selectedModel: 'llama3.2:3b',
      isInserted: false,
    })
  })

  it('has correct initial state', () => {
    const state = useSidebarStore.getState()
    expect(state.ticketData).toBeNull()
    expect(state.isTicketPage).toBe(false)
    expect(state.reply).toBe('')
    expect(state.isGenerating).toBe(false)
    expect(state.generateError).toBeNull()
    expect(state.lastResponse).toBeNull()
    expect(state.selectedModel).toBe('llama3.2:3b')
    expect(state.isInserted).toBe(false)
  })

  it('sets ticket data', () => {
    const ticket = {
      subject: 'Test',
      description: 'Test desc',
      requesterName: 'Jane',
      category: 'Network',
      status: 'Open',
      ticketUrl: 'http://helpdesk.local/ticket/1',
      customFields: {},
    }
    useSidebarStore.getState().setTicketData(ticket)
    expect(useSidebarStore.getState().ticketData).toEqual(ticket)
  })

  it('sets isTicketPage', () => {
    useSidebarStore.getState().setIsTicketPage(true)
    expect(useSidebarStore.getState().isTicketPage).toBe(true)
  })

  it('sets reply', () => {
    useSidebarStore.getState().setReply('Hello, try restarting.')
    expect(useSidebarStore.getState().reply).toBe('Hello, try restarting.')
  })

  it('sets selectedModel', () => {
    useSidebarStore.getState().setSelectedModel('llama3.1:8b')
    expect(useSidebarStore.getState().selectedModel).toBe('llama3.1:8b')
  })

  it('sets isGenerating', () => {
    useSidebarStore.getState().setIsGenerating(true)
    expect(useSidebarStore.getState().isGenerating).toBe(true)
  })

  it('sets generateError', () => {
    useSidebarStore.getState().setGenerateError('Ollama down')
    expect(useSidebarStore.getState().generateError).toBe('Ollama down')
  })

  it('reset clears transient state but preserves ticket and model', () => {
    const ticket = {
      subject: 'Test',
      description: 'Desc',
      requesterName: 'Jane',
      category: 'Net',
      status: 'Open',
      ticketUrl: 'http://helpdesk.local/ticket/1',
      customFields: {},
    }
    useSidebarStore.getState().setTicketData(ticket)
    useSidebarStore.getState().setSelectedModel('llama3.1:8b')
    useSidebarStore.getState().setReply('Some reply')
    useSidebarStore.getState().setIsGenerating(true)
    useSidebarStore.getState().setGenerateError('Error')
    useSidebarStore.getState().setIsInserted(true)

    useSidebarStore.getState().reset()

    const state = useSidebarStore.getState()
    expect(state.reply).toBe('')
    expect(state.isGenerating).toBe(false)
    expect(state.generateError).toBeNull()
    expect(state.lastResponse).toBeNull()
    expect(state.isInserted).toBe(false)
    // These should be preserved
    expect(state.ticketData).toEqual(ticket)
    expect(state.selectedModel).toBe('llama3.1:8b')
  })
})
