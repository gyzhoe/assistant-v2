import { useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient } from '../../lib/api-client'

export function useGenerateReply() {
  const ticketData = useSidebarStore((s) => s.ticketData)
  const selectedModel = useSidebarStore((s) => s.selectedModel)
  const setReply = useSidebarStore((s) => s.setReply)
  const setIsGenerating = useSidebarStore((s) => s.setIsGenerating)
  const setGenerateError = useSidebarStore((s) => s.setGenerateError)
  const setLastResponse = useSidebarStore((s) => s.setLastResponse)
  const setIsInserted = useSidebarStore((s) => s.setIsInserted)
  const setAbortController = useSidebarStore((s) => s.setAbortController)
  const setIsEditingReply = useSidebarStore((s) => s.setIsEditingReply)

  const generate = useCallback(async () => {
    if (!ticketData) return

    const ctrl = new AbortController()
    setAbortController(ctrl)
    setIsGenerating(true)
    setGenerateError(null)
    setReply('')
    setIsInserted(false)
    setIsEditingReply(false)

    try {
      const response = await apiClient.generate({
        ticket_subject: ticketData.subject,
        ticket_description: ticketData.description,
        requester_name: ticketData.requesterName,
        category: ticketData.category,
        status: ticketData.status,
        model: selectedModel,
        max_context_docs: 5,
        stream: false,
      }, ctrl.signal)
      setReply(response.reply)
      setLastResponse(response)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return
      }
      const message = err instanceof Error ? err.message : 'Failed to generate reply'
      setGenerateError(message)
    } finally {
      setIsGenerating(false)
      setAbortController(null)
    }
  }, [ticketData, selectedModel, setReply, setIsGenerating, setGenerateError, setLastResponse, setIsInserted, setAbortController, setIsEditingReply])

  return { generate }
}
