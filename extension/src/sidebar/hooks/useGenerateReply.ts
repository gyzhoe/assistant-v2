import { useCallback, useRef } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { useSettings } from './useSettings'
import { apiClient, ApiError } from '../../lib/api-client'
import { parseErrorDetail } from '../../lib/error-utils'
import { debugLog, debugError } from '../../shared/constants'
import type { ContextDoc } from '../../shared/types'

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

  // Ref-based token accumulation for performance (no setState per token)
  const replyRef = useRef('')

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
    replyRef.current = ''

    let contextDocs: ContextDoc[] = []
    let latencyMs = 0

    try {
      const stream = await apiClient.generateStream({
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
      }, ctrl.signal)

      for await (const event of stream) {
        if (ctrl.signal.aborted) return

        switch (event.type) {
          case 'meta':
            contextDocs = event.context_docs
            debugLog('SSE meta: received', event.context_docs.length, 'context docs')
            break
          case 'token':
            replyRef.current += event.content
            setReply(replyRef.current)
            break
          case 'error':
            // Preserve partial text and show inline error
            setGenerateError(event.message)
            debugError('SSE error:', event.error_code, event.message)
            return
          case 'done':
            latencyMs = event.latency_ms
            debugLog('SSE done: latency', event.latency_ms, 'ms')
            break
        }
      }

      const finalReply = replyRef.current
      setLastResponse({
        reply: finalReply,
        model_used: selectedModel,
        context_docs: contextDocs,
        latency_ms: latencyMs,
      })

      // Persist reply for this ticket so it survives navigation
      if (ticketData.ticketUrl) {
        saveReplyForTicket(ticketData.ticketUrl)
      }

      // Auto-insert: send INSERT_REPLY message to content script after successful generation
      if (settings.autoInsert && finalReply) {
        debugLog('Auto-insert enabled, sending INSERT_REPLY')
        chrome.runtime.sendMessage({ type: 'INSERT_REPLY', payload: { text: finalReply } }).catch((err: unknown) => {
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
        if (body?.['error_code'] === 'LLM_DOWN') {
          message = 'LLM server is not running. Please start it and try again.'
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
