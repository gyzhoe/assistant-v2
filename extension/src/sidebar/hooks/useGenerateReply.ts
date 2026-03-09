import { useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { useSettings } from './useSettings'
import { apiClient, ApiError } from '../../lib/api-client'
import { parseErrorDetail } from '../../lib/error-utils'
import { debugLog, debugError } from '../../shared/constants'
import type { GenerateRequest } from '../../shared/types'

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

    const req: GenerateRequest = {
      ticket_subject: ticketData.subject,
      ticket_description: ticketData.description,
      requester_name: ticketData.requesterName,
      category: ticketData.category,
      status: ticketData.status,
      model: selectedModel,
      max_context_docs: 5,
      stream: true,
      include_web_context: true,
      prompt_suffix: settings.promptSuffix,
      custom_fields: ticketData.customFields,
      pinned_article_ids: pinnedArticles.map((a) => a.article_id),
      notes: ticketData.notes.slice(0, 20).map((n) => ({
        author: n.author,
        text: n.text,
        type: n.type,
        date: n.date,
        note_id: n.noteId,
        time_spent: n.timeSpent,
      })),
    }

    try {
      for await (const event of apiClient.generateStream(req, ctrl.signal)) {
        if (ctrl.signal.aborted) return

        switch (event.type) {
          case 'meta':
            setLastResponse({
              reply: '',
              model_used: selectedModel,
              context_docs: event.context_docs,
              latency_ms: 0,
            })
            break
          case 'token': {
            const current = useSidebarStore.getState().reply
            setReply(current + event.content)
            break
          }
          case 'done': {
            const finalReply = useSidebarStore.getState().reply
            const lastResp = useSidebarStore.getState().lastResponse
            setLastResponse({
              reply: finalReply,
              model_used: lastResp?.model_used ?? selectedModel,
              context_docs: lastResp?.context_docs ?? [],
              latency_ms: event.latency_ms,
            })
            debugLog('Generation complete:', event.latency_ms, 'ms')

            if (ticketData.ticketUrl) {
              saveReplyForTicket(ticketData.ticketUrl)
            }

            if (settings.autoInsert && finalReply) {
              debugLog('Auto-insert enabled, sending INSERT_REPLY')
              chrome.runtime.sendMessage({ type: 'INSERT_REPLY', payload: { text: finalReply } }).catch((err: unknown) => {
                debugError('Auto-insert failed:', err)
              })
            }
            break
          }
          case 'error':
            setGenerateError(
              event.error_code === 'LLM_DOWN'
                ? 'LLM server is not running. Please start it and try again.'
                : event.message || 'Generation failed'
            )
            break
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return
      }
      let message = 'Failed to generate reply'
      let title: string | undefined
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown>
        if (body?.['error_code'] === 'LLM_DOWN') {
          message = 'LLM server is not running. Please start it and try again.'
          title = 'LLM Server Offline'
        } else {
          const parsed = parseErrorDetail(body)
          message = parsed !== 'An unexpected error occurred'
            ? parsed
            : `Generation failed (${err.status})`
          title = 'Generation Failed'
        }
      } else if (err instanceof TypeError && err.message === 'Failed to fetch') {
        message = 'Network error — check connection and backend status'
        title = 'Connection Error'
      } else if (err instanceof Error) {
        message = err.message
        title = 'Generation Failed'
      }
      setGenerateError(title ? `${title}|${message}` : message)
    } finally {
      setIsGenerating(false)
      setAbortController(null)
    }
  // Zustand setters (setReply, setIsGenerating, etc.) are stable references — safe to omit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketData, selectedModel, pinnedArticles, settings.promptSuffix, settings.autoInsert])

  return { generate }
}
