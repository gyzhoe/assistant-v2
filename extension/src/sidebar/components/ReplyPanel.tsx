import React, { useEffect, useState, useMemo } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { useTicketData } from '../hooks/useTicketData'
import { useGenerateReply } from '../hooks/useGenerateReply'
import { TicketContext } from './TicketContext'
import { ModelSelector } from './ModelSelector'
import { SkeletonLoader } from './SkeletonLoader'
import { InsertButton } from './InsertButton'
import { ErrorState } from './ErrorState'
import { apiClient } from '../../lib/api-client'

type HealthStatus = 'loading' | 'ready' | 'error'

export function ReplyPanel(): React.ReactElement {
  useTicketData()
  const { generate } = useGenerateReply()

  const ticketData = useSidebarStore((s) => s.ticketData)
  const isTicketPage = useSidebarStore((s) => s.isTicketPage)
  const reply = useSidebarStore((s) => s.reply)
  const isGenerating = useSidebarStore((s) => s.isGenerating)
  const generateError = useSidebarStore((s) => s.generateError)
  const selectedModel = useSidebarStore((s) => s.selectedModel)

  const [healthStatus, setHealthStatus] = useState<HealthStatus>('loading')
  const [ollamaReachable, setOllamaReachable] = useState(true)

  useEffect(() => {
    apiClient.health().then((h) => {
      setOllamaReachable(h.ollama_reachable)
      setHealthStatus(h.ollama_reachable ? 'ready' : 'error')
    }).catch(() => {
      setOllamaReachable(false)
      setHealthStatus('error')
    })
  }, [])

  const readiness = useMemo(() => [
    { label: 'Ticket detected', ok: Boolean(isTicketPage && ticketData) },
    { label: 'Backend connected', ok: ollamaReachable },
    { label: 'Model selected', ok: selectedModel.length > 0 },
  ], [isTicketPage, ticketData, ollamaReachable, selectedModel])

  const chipClass =
    healthStatus === 'ready' ? 'ok' :
    healthStatus === 'loading' ? 'pending' : 'error'

  const chipLabel =
    healthStatus === 'ready' ? 'Ready' :
    healthStatus === 'loading' ? 'Checking' : 'Attention'

  return (
    <>
      {/* Session readiness */}
      <section className="panel" aria-label="Workflow readiness">
        <div className="section-heading-row">
          <h2 className="section-heading">Session readiness</h2>
          <span className={`status-chip ${chipClass}`}>{chipLabel}</span>
        </div>
        {!ollamaReachable && healthStatus === 'error' && (
          <p className="support-text error-text" role="alert" aria-live="assertive">
            <strong>Ollama is not reachable.</strong> Start Ollama and ensure the backend is running, then refresh.
          </p>
        )}
        <div className="badge-grid">
          {readiness.map((r) => (
            <span key={r.label} className={`badge${r.ok ? ' ok' : ''}`}>
              {r.ok ? '\u2713' : '\u2022'} {r.label}
            </span>
          ))}
        </div>
      </section>

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
          aria-busy={isGenerating}
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
