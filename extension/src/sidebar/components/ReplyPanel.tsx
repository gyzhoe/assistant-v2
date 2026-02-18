import React, { useEffect, useState } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { useTicketData } from '../hooks/useTicketData'
import { useGenerateReply } from '../hooks/useGenerateReply'
import { TicketContext } from './TicketContext'
import { ModelSelector } from './ModelSelector'
import { SkeletonLoader } from './SkeletonLoader'
import { InsertButton } from './InsertButton'
import { ErrorState } from './ErrorState'
import { apiClient } from '../../lib/api-client'

export function ReplyPanel(): React.ReactElement {
  useTicketData()
  const { generate } = useGenerateReply()

  const ticketData = useSidebarStore((s) => s.ticketData)
  const isTicketPage = useSidebarStore((s) => s.isTicketPage)
  const reply = useSidebarStore((s) => s.reply)
  const isGenerating = useSidebarStore((s) => s.isGenerating)
  const generateError = useSidebarStore((s) => s.generateError)

  // Ollama health check on mount
  const [ollamaDown, setOllamaDown] = useState(false)
  useEffect(() => {
    apiClient.health().then((h) => {
      setOllamaDown(!h.ollama_reachable)
    }).catch(() => {
      setOllamaDown(true)
    })
  }, [])

  if (!isTicketPage) {
    return (
      <div className="p-4 text-center text-neutral-500 text-xs mt-8">
        <p className="mb-1">No ticket detected.</p>
        <p>Navigate to a WHD ticket page to use the assistant.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Ollama-down banner */}
      {ollamaDown && (
        <div
          className="mx-2 mt-2 px-3 py-2 bg-amber-50 border border-amber-300 rounded text-xs text-amber-800"
          role="alert"
          aria-live="assertive"
        >
          <span className="font-semibold">Ollama is not reachable.</span>{' '}
          Start Ollama and ensure the backend is running, then refresh.
        </div>
      )}

      {ticketData && <TicketContext ticket={ticketData} />}
      <ModelSelector />

      {/* Generate button */}
      <div className="px-3 py-2 border-b border-neutral-100">
        <button
          onClick={generate}
          disabled={isGenerating || !ticketData}
          className="w-full py-1.5 px-3 rounded text-xs font-semibold bg-accent text-white hover:bg-accent-hover disabled:bg-neutral-300 disabled:text-neutral-500 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          aria-label="Generate AI reply for this ticket"
          aria-busy={isGenerating}
        >
          {isGenerating ? 'Generating…' : 'Generate Reply'}
        </button>
      </div>

      {/* Reply area */}
      <div className="flex-1 overflow-y-auto">
        {isGenerating && <SkeletonLoader />}

        {generateError && !isGenerating && (
          <ErrorState message={generateError} onRetry={generate} />
        )}

        {reply && !isGenerating && (
          <div className="p-3 flex flex-col gap-2">
            <div
              className="text-xs text-neutral-700 whitespace-pre-wrap leading-relaxed bg-white border border-neutral-200 rounded p-2.5"
              aria-live="polite"
              aria-label="Generated reply"
            >
              {reply}
            </div>
            <InsertButton />
          </div>
        )}
      </div>
    </div>
  )
}
