import React from 'react'
import type { TicketData } from '../../shared/types'

interface TicketContextProps {
  ticket: TicketData
}

export function TicketContext({ ticket }: TicketContextProps): React.ReactElement {
  return (
    <div className="px-3 py-2 border-b border-neutral-200 bg-white">
      <p className="font-semibold text-neutral-800 truncate text-xs leading-5" title={ticket.subject}>
        {ticket.subject || <span className="text-neutral-400 italic">No subject</span>}
      </p>
      <div className="flex gap-2 mt-1 flex-wrap">
        {ticket.category && (
          <span className="text-xs text-neutral-500 bg-neutral-100 px-1.5 py-0.5 rounded">
            {ticket.category}
          </span>
        )}
        {ticket.status && (
          <span className="text-xs text-neutral-500 bg-neutral-100 px-1.5 py-0.5 rounded">
            {ticket.status}
          </span>
        )}
        {ticket.requesterName && (
          <span className="text-xs text-neutral-500 truncate">
            {ticket.requesterName}
          </span>
        )}
      </div>
    </div>
  )
}
