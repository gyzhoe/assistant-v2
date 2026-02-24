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
          {isGenerating ? 'Generating…' : 'Generate Reply'}
        </button>
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
          </div>
        )}

        {reply && !isGenerating && (
          <div className="reply-box" aria-live="polite" aria-label="Generated reply">
            {reply}
          </div>
        )}

        <InsertButton />
      </section>
    </>
  )
}
