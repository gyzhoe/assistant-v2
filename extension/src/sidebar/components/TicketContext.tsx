import React, { useState } from 'react'
import type { TicketData } from '../../shared/types'

interface TicketContextProps {
  ticket: TicketData
}

export function TicketContext({ ticket }: TicketContextProps): React.ReactElement {
  const [descExpanded, setDescExpanded] = useState(false)
  const hasDescription = Boolean(ticket.description)

  return (
    <div className="context-card">
      <p className="subject" title={ticket.subject}>
        {ticket.subject || <span className="text-empty">No subject</span>}
      </p>
      <div className="meta-row">
        {ticket.category && <span>{ticket.category}</span>}
        {ticket.status && <span>{ticket.status}</span>}
        {ticket.requesterName && <span>{ticket.requesterName}</span>}
      </div>
      {hasDescription && (
        <div className="ticket-desc">
          <p className={`ticket-desc-text${descExpanded ? ' ticket-desc-expanded' : ''}`}>
            {ticket.description}
          </p>
          <button
            type="button"
            className="link-btn ticket-desc-toggle"
            onClick={() => setDescExpanded((e) => !e)}
            aria-expanded={descExpanded}
          >
            {descExpanded ? 'Show less' : 'Show more'}
          </button>
        </div>
      )}
    </div>
  )
}
