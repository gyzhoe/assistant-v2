import React, { useState } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { useTicketData } from '../hooks/useTicketData'
import { useGenerateReply } from '../hooks/useGenerateReply'
import { useSubmitFeedback } from '../hooks/useSubmitFeedback'
import { TicketContext } from './TicketContext'
import { KBContextPicker } from './KBContextPicker'
import { ModelSelector } from './ModelSelector'
import { SkeletonLoader } from './SkeletonLoader'
import { InsertButton } from './InsertButton'
import { ErrorState } from './ErrorState'

export function ReplyPanel(): React.ReactElement {
  useTicketData()
  const { generate } = useGenerateReply()
  const { submitRating, feedbackError, ratingConfirmed, ratingRemoved } = useSubmitFeedback()
  const [contextCollapsed, setContextCollapsed] = useState(false)

  const pinnedCount = useSidebarStore((s) => s.pinnedArticles.length)
  const ticketData = useSidebarStore((s) => s.ticketData)
  const isTicketPage = useSidebarStore((s) => s.isTicketPage)
  const reply = useSidebarStore((s) => s.reply)
  const isGenerating = useSidebarStore((s) => s.isGenerating)
  const generateError = useSidebarStore((s) => s.generateError)
  const isInserted = useSidebarStore((s) => s.isInserted)
  const cancelGeneration = useSidebarStore((s) => s.cancelGeneration)
  const isEditingReply = useSidebarStore((s) => s.isEditingReply)
  const setIsEditingReply = useSidebarStore((s) => s.setIsEditingReply)
  const setReply = useSidebarStore((s) => s.setReply)
  const replyRating = useSidebarStore((s) => s.replyRating)

  return (
    <>
      {/* Ticket context */}
      <section className="panel" aria-label="Ticket details">
        <button
          className="section-heading-row collapsible-trigger"
          onClick={() => setContextCollapsed((c) => !c)}
          aria-expanded={!contextCollapsed}
          aria-controls="ticket-context-body"
        >
          <h2 className="section-heading">Ticket context</h2>
          <div className="heading-right">
            {pinnedCount > 0 && (
              <span className="status-chip ok">{pinnedCount} pinned</span>
            )}
            <span className={`chevron ${contextCollapsed ? '' : 'open'}`} aria-hidden="true" />
          </div>
        </button>
        {!contextCollapsed && (
          <div id="ticket-context-body" className="collapsible-body">
            {!isTicketPage && (
              <p className="support-text">Open a WHD ticket page to begin. This panel updates automatically.</p>
            )}
            {ticketData && <TicketContext ticket={ticketData} />}
            <KBContextPicker />
          </div>
        )}
      </section>

      {/* Compose reply */}
      <section className="panel" aria-label="Generation controls">
        <h2 className="section-heading">Compose reply</h2>
        <ModelSelector />
        <button
          onClick={generate}
          disabled={isGenerating || !ticketData}
          className="primary-btn"
          aria-label="Generate AI reply for this ticket"
          aria-busy={isGenerating ? 'true' : undefined}
        >
          {isGenerating ? 'Generating\u2026' : 'Generate Reply'}
        </button>
        {isGenerating && (
          <button
            type="button"
            className="secondary-btn cancel-btn"
            onClick={cancelGeneration}
            aria-label="Cancel reply generation"
          >
            Cancel
          </button>
        )}
        {generateError && !isGenerating && (
          <ErrorState message={generateError} onRetry={generate} />
        )}
      </section>

      {/* Draft output */}
      <section className="panel" aria-label="Generated reply">
        <h2 className="section-heading">Draft output</h2>
        {isGenerating && <SkeletonLoader />}

        {!isGenerating && !reply && (
          <div className="reply-box">
            <span className="reply-placeholder">
              Your generated reply will appear here.
            </span>
            <span className="reply-hint">Press Alt+Shift+H to toggle sidebar</span>
          </div>
        )}

        {reply && !isGenerating && (
          <div className="draft-panel">
            <div className="draft-header">
              <span className="draft-label">Draft Reply</span>
              <div className="draft-actions">
                <div className="rating-group" role="group" aria-label="Rate this reply">
                  <button
                    type="button"
                    className={`rating-btn${replyRating === 'good' ? ' selected' : ''}${replyRating === 'bad' ? ' dimmed' : ''}`}
                    onClick={() => submitRating('good')}
                    aria-label="Rate as helpful"
                    aria-pressed={replyRating === 'good'}
                  >
                    &#x1F44D;
                  </button>
                  <button
                    type="button"
                    className={`rating-btn${replyRating === 'bad' ? ' selected' : ''}${replyRating === 'good' ? ' dimmed' : ''}`}
                    onClick={() => submitRating('bad')}
                    aria-label="Rate as unhelpful"
                    aria-pressed={replyRating === 'bad'}
                  >
                    &#x1F44E;
                  </button>
                </div>
                <div aria-live="polite" className="rating-feedback-region">
                  {ratingConfirmed && (
                    <span className="rating-saved">&#x2713; Saved</span>
                  )}
                  {ratingRemoved && !ratingConfirmed && (
                    <span className="rating-removed">&#x2713; Removed</span>
                  )}
                  {feedbackError && !ratingConfirmed && !ratingRemoved && (
                    <span className="support-text error-text" role="alert">{feedbackError}</span>
                  )}
                </div>
                <button
                  type="button"
                  className="secondary-btn draft-toggle"
                  onClick={() => setIsEditingReply(!isEditingReply)}
                  aria-label={isEditingReply ? 'Preview reply' : 'Edit reply'}
                >
                  {isEditingReply ? 'Preview' : 'Edit'}
                </button>
              </div>
            </div>
            {isEditingReply ? (
              <textarea
                className="reply-edit"
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                rows={8}
                aria-label="Edit generated reply"
              />
            ) : (
              <div className="reply-box" aria-live="polite" aria-label="Generated reply">
                {reply}
              </div>
            )}
            {!isInserted && <InsertButton />}
          </div>
        )}
      </section>
    </>
  )
}
