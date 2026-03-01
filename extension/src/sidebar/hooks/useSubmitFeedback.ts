import { useCallback, useRef, useState } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient } from '../../lib/api-client'
import { debugError, debugLog } from '../../shared/constants'

const RATING_CONFIRMED_DURATION_MS = 2000

export function useSubmitFeedback() {
  const ticketData = useSidebarStore((s) => s.ticketData)
  const reply = useSidebarStore((s) => s.reply)
  const replyRating = useSidebarStore((s) => s.replyRating)
  const setReplyRating = useSidebarStore((s) => s.setReplyRating)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const [ratingConfirmed, setRatingConfirmed] = useState(false)
  const [ratingRemoved, setRatingRemoved] = useState(false)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const feedbackDocIdRef = useRef<string | null>(null)

  const submitRating = useCallback(async (rating: 'good' | 'bad') => {
    // Toggle off if the same rating is clicked again — delete from backend
    if (replyRating === rating) {
      setReplyRating(null)
      setFeedbackError(null)
      setRatingConfirmed(false)
      setRatingRemoved(false)

      const docId = feedbackDocIdRef.current
      if (docId) {
        try {
          await apiClient.deleteFeedback(docId)
          feedbackDocIdRef.current = null
          if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
          setRatingRemoved(true)
          confirmTimerRef.current = setTimeout(() => setRatingRemoved(false), RATING_CONFIRMED_DURATION_MS)
          debugLog('Feedback deleted: id=%s', docId)
        } catch (err) {
          debugError('Failed to delete feedback:', err)
          setFeedbackError('Remove failed')
        }
      }
      return
    }

    setReplyRating(rating)
    setFeedbackError(null)
    setRatingConfirmed(false)
    setRatingRemoved(false)

    if (!ticketData || !reply) return

    try {
      const result = await apiClient.submitFeedback({
        ticket_subject: ticketData.subject,
        ticket_description: ticketData.description,
        category: ticketData.category,
        reply,
        rating,
      })
      feedbackDocIdRef.current = result.id
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

  return { submitRating, feedbackError, ratingConfirmed, ratingRemoved }
}
