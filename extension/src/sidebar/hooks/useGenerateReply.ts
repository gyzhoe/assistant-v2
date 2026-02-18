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

  const generate = useCallback(async () => {
    if (!ticketData) return

    setIsGenerating(true)
    setGenerateError(null)
    setReply('')
    setIsInserted(false)

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
      })
      setReply(response.reply)
      setLastResponse(response)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate reply'
      setGenerateError(message)
    } finally {
      setIsGenerating(false)
    }
  }, [ticketData, selectedModel, setReply, setIsGenerating, setGenerateError, setLastResponse, setIsInserted])

  return { generate }
}
