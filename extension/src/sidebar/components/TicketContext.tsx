import React from 'react'
import type { TicketData } from '../../shared/types'

interface TicketContextProps {
  ticket: TicketData
}

export function TicketContext({ ticket }: TicketContextProps): React.ReactElement {
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
    </div>
  )
}
