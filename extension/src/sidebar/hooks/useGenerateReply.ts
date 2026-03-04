import { useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { useSettings } from './useSettings'
import { apiClient, ApiError } from '../../lib/api-client'
import { parseErrorDetail } from '../../lib/error-utils'
import { debugLog, debugError } from '../../shared/constants'

export function useGenerateReply() {
  const ticketData = useSidebarStore((s) => s.ticketData)
  const selectedModel = useSidebarStore((s) => s.selectedModel)
  const pinnedArticles = useSidebarStore((s) => s.pinnedArticles)
  const setReply = useSidebarStore((s) => s.setReply)
  const setIsGenerating = useSidebarStore((s) => s.setIsGenerating)
  const setGenerateError = useSidebarStore((s) => s.setGenerateError)
  const setLastResponse = useSidebarStore((s) => s.setLastResponse)
  const setIsInserted = useSidebarStore((s) => s.setIsInserted)
  const setAbortController = useSidebarStore((s) => s.setAbortController)
  const setIsEditingReply = useSidebarStore((s) => s.setIsEditingReply)
  const setReplyRating = useSidebarStore((s) => s.setReplyRating)
  const saveReplyForTicket = useSidebarStore((s) => s.saveReplyForTicket)
  const { settings } = useSettings()

  const generate = useCallback(async () => {
    if (!ticketData) return

    const ctrl = new AbortController()
    setAbortController(ctrl)
    setIsGenerating(true)
    setGenerateError(null)
    setReply('')
    setIsInserted(false)
    setIsEditingReply(false)
    setReplyRating(null)

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
        include_web_context: true,
        prompt_suffix: settings.promptSuffix,
        custom_fields: ticketData.customFields,
        pinned_article_ids: pinnedArticles.map((a) => a.article_id),
      }, ctrl.signal)
      setReply(response.reply)
      setLastResponse(response)

      // Persist reply for this ticket so it survives navigation
      if (ticketData.ticketUrl) {
        saveReplyForTicket(ticketData.ticketUrl)
      }

      // Auto-insert: send INSERT_REPLY message to content script after successful generation
      if (settings.autoInsert && response.reply) {
        debugLog('Auto-insert enabled, sending INSERT_REPLY')
        chrome.runtime.sendMessage({ type: 'INSERT_REPLY', payload: { text: response.reply } }).catch((err: unknown) => {
          debugError('Auto-insert failed:', err)
        })
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return
      }
      let message = 'Failed to generate reply'
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown>
        if (body?.['error_code'] === 'OLLAMA_DOWN' || err.status === 503) {
          message = 'Ollama is not running. Please start it and try again.'
        } else {
          const parsed = parseErrorDetail(body)
          message = parsed !== 'An unexpected error occurred'
            ? parsed
            : `Generation failed (${err.status})`
        }
      } else if (err instanceof TypeError && err.message === 'Failed to fetch') {
        message = 'Network error — check connection and backend status'
      } else if (err instanceof Error) {
        message = err.message
      }
      setGenerateError(message)
    } finally {
      setIsGenerating(false)
      setAbortController(null)
    }
  // Zustand setters (setReply, setIsGenerating, etc.) are stable references — safe to omit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketData, selectedModel, pinnedArticles, settings.promptSuffix, settings.autoInsert])

  return { generate }
}
