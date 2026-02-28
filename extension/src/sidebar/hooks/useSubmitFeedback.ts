import { useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient } from '../../lib/api-client'
import { debugError } from '../../shared/constants'

export function useSubmitFeedback() {
  const ticketData = useSidebarStore((s) => s.ticketData)
  const reply = useSidebarStore((s) => s.reply)
  const setReplyRating = useSidebarStore((s) => s.setReplyRating)

  const submitRating = useCallback(async (rating: 'good' | 'bad') => {
    setReplyRating(rating)

    if (!ticketData || !reply) return

    try {
      await apiClient.submitFeedback({
        ticket_subject: ticketData.subject,
        ticket_description: ticketData.description,
        category: ticketData.category,
        reply,
        rating,
      })
    } catch (err) {
      debugError('Failed to submit feedback:', err)
      setReplyRating(null)
    }
  }, [ticketData, reply, setReplyRating])

  return { submitRating }
}
