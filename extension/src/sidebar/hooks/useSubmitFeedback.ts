import { useCallback, useRef, useState } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient } from '../../lib/api-client'
import { debugError } from '../../shared/constants'

const RATING_CONFIRMED_DURATION_MS = 2000

export function useSubmitFeedback() {
  const ticketData = useSidebarStore((s) => s.ticketData)
  const reply = useSidebarStore((s) => s.reply)
  const replyRating = useSidebarStore((s) => s.replyRating)
  const setReplyRating = useSidebarStore((s) => s.setReplyRating)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const [ratingConfirmed, setRatingConfirmed] = useState(false)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const submitRating = useCallback(async (rating: 'good' | 'bad') => {
    // Toggle off if the same rating is clicked again
    if (replyRating === rating) {
      setReplyRating(null)
      setFeedbackError(null)
      setRatingConfirmed(false)
      return
    }

    setReplyRating(rating)
    setFeedbackError(null)
    setRatingConfirmed(false)

    if (!ticketData || !reply) return

    try {
      await apiClient.submitFeedback({
        ticket_subject: ticketData.subject,
        ticket_description: ticketData.description,
        category: ticketData.category,
        reply,
        rating,
      })
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
      setRatingConfirmed(true)
      confirmTimerRef.current = setTimeout(() => setRatingConfirmed(false), RATING_CONFIRMED_DURATION_MS)
    } catch (err) {
      debugError('Failed to submit feedback:', err)
      setFeedbackError('Rating not saved')
    }
  // setReplyRating is a stable Zustand setter — safe to omit from deps.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketData, reply, replyRating])

  return { submitRating, feedbackError, ratingConfirmed }
}
