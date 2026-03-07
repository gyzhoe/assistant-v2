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
  const feedbackDocId = useSidebarStore((s) => s.feedbackDocId)
  const setFeedbackDocId = useSidebarStore((s) => s.setFeedbackDocId)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const [ratingConfirmed, setRatingConfirmed] = useState(false)
  const [ratingRemoved, setRatingRemoved] = useState(false)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const submitRating = useCallback(async (rating: 'good' | 'bad') => {
    // Toggle off if the same rating is clicked again — delete from backend
    if (replyRating === rating) {
      setReplyRating(null)
      setFeedbackError(null)
      setRatingConfirmed(false)
      setRatingRemoved(false)

      if (feedbackDocId) {
        try {
          await apiClient.deleteFeedback(feedbackDocId)
          setFeedbackDocId(null)
          if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
          setRatingRemoved(true)
          confirmTimerRef.current = setTimeout(() => setRatingRemoved(false), RATING_CONFIRMED_DURATION_MS)
          debugLog('Feedback deleted: id=%s', feedbackDocId)
        } catch (err) {
          debugError('Failed to delete feedback:', err)
          setFeedbackError('Remove failed')
        }
      }
      return
    }

    setReplyRating(rating)
    setRatingConfirmed(false)
    setRatingRemoved(false)

    if (!ticketData || !reply) {
      setFeedbackError('Open a ticket page to save ratings')
      return
    }
    setFeedbackError(null)

    try {
      const result = await apiClient.submitFeedback({
        ticket_subject: ticketData.subject,
        ticket_description: ticketData.description,
        category: ticketData.category,
        reply,
        rating,
      })
      setFeedbackDocId(result.id)
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
      setRatingConfirmed(true)
      confirmTimerRef.current = setTimeout(() => setRatingConfirmed(false), RATING_CONFIRMED_DURATION_MS)
    } catch (err) {
      debugError('Failed to submit feedback:', err)
      setFeedbackError('Rating not saved')
    }
  // setReplyRating and setFeedbackDocId are stable Zustand setters — safe to omit from deps.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketData, reply, replyRating, feedbackDocId])

  return { submitRating, feedbackError, ratingConfirmed, ratingRemoved }
}
