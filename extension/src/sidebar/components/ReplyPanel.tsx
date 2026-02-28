import React from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { useTicketData } from '../hooks/useTicketData'
import { useGenerateReply } from '../hooks/useGenerateReply'
import { TicketContext } from './TicketContext'
import { ModelSelector } from './ModelSelector'
import { SkeletonLoader } from './SkeletonLoader'
import { InsertButton } from './InsertButton'
import { ErrorState } from './ErrorState'

export function ReplyPanel(): React.ReactElement {
  useTicketData()
  const { generate } = useGenerateReply()

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

  return (
    <>
      {/* Ticket context */}
      <section className="panel" aria-label="Ticket details">
        <h2 className="section-heading">Ticket context</h2>
        {!isTicketPage && (
          <p className="support-text">Open a WHD ticket page to begin. This panel updates automatically.</p>
        )}
        {ticketData && <TicketContext ticket={ticketData} />}
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
              <button
                type="button"
                className="secondary-btn draft-toggle"
                onClick={() => setIsEditingReply(!isEditingReply)}
                aria-label={isEditingReply ? 'Preview reply' : 'Edit reply'}
              >
                {isEditingReply ? 'Preview' : 'Edit'}
              </button>
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
