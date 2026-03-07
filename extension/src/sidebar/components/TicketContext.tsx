import React, { useState } from 'react'
import type { TicketData, NoteData } from '../../shared/types'

interface TicketContextProps {
  ticket: TicketData
}

const NOTE_TYPE_LABELS: Record<NoteData['type'], string> = {
  client: 'Client',
  tech_visible: 'Tech (visible)',
  tech_internal: 'Tech (internal)',
}

function stripUNumber(author: string): string {
  return author.replace(/\s*-\s*u\d+$/, '')
}

export function TicketContext({ ticket }: TicketContextProps): React.ReactElement {
  const [descExpanded, setDescExpanded] = useState(false)
  const [notesExpanded, setNotesExpanded] = useState(ticket.notes.length <= 5)
  const [expandedNoteIds, setExpandedNoteIds] = useState<Set<string>>(new Set())
  const hasDescription = Boolean(ticket.description)
  const customFieldEntries = Object.entries(ticket.customFields)
  const hasCustomFields = customFieldEntries.length > 0
  const hasNotes = ticket.notes.length > 0

  const toggleNoteExpand = (noteId: string) => {
    setExpandedNoteIds((prev) => {
      const next = new Set(prev)
      if (next.has(noteId)) {
        next.delete(noteId)
      } else {
        next.add(noteId)
      }
      return next
    })
  }

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

      {hasCustomFields && (
        <div className="ticket-custom-fields">
          {customFieldEntries.map(([key, value]) => (
            <div key={key} className="custom-field-row">
              <span className="custom-field-key">{key}</span>
              <span className="custom-field-value">{value}</span>
            </div>
          ))}
        </div>
      )}

      {hasNotes && (
        <div className="ticket-notes-section">
          <button
            type="button"
            className="link-btn ticket-notes-toggle"
            onClick={() => setNotesExpanded((e) => !e)}
            aria-expanded={notesExpanded}
          >
            <span>Notes ({ticket.notes.length})</span>
            <span className={`chevron${notesExpanded ? ' open' : ''}`} />
          </button>
          {notesExpanded && (
            <div className="ticket-notes-list">
              {ticket.notes.map((note, i) => {
                const id = note.noteId || String(i)
                const isExpanded = expandedNoteIds.has(id)
                return (
                  <div key={id} className="ticket-note">
                    <div className="ticket-note-header">
                      <span
                        className={`note-type-dot note-type-${note.type}`}
                        title={NOTE_TYPE_LABELS[note.type]}
                      />
                      <span className="note-author">{stripUNumber(note.author)}</span>
                      <span className="note-date">{note.date}</span>
                    </div>
                    <p className={`note-text${isExpanded ? ' note-text-expanded' : ''}`}>
                      {note.text}
                    </p>
                    {note.text.length > 200 && (
                      <button
                        type="button"
                        className="link-btn note-expand-btn"
                        onClick={() => toggleNoteExpand(id)}
                      >
                        {isExpanded ? 'Show less' : 'Show more'}
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
