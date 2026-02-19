import React, { useEffect, useRef } from 'react'
import { ReplyPanel } from './components/ReplyPanel'
import { ErrorBoundary } from './components/ErrorBoundary'

export default function App(): React.ReactElement {
  const mainRef = useRef<HTMLElement>(null)

  useEffect(() => {
    // Focus the main region on sidebar open so keyboard users start in the right place
    mainRef.current?.focus()
  }, [])

  return (
    <ErrorBoundary>
      <div className="flex flex-col h-screen bg-neutral-50 text-neutral-900 font-sans text-sm">
        <header
          className="flex items-center gap-2 px-3 py-2 border-b border-neutral-200 bg-white"
          role="banner"
        >
          <div
            className="w-5 h-5 rounded flex items-center justify-center text-white text-xs font-bold flex-shrink-0 bg-accent"
            aria-hidden="true"
          >
            AI
          </div>
          <h1 className="text-sm font-semibold text-neutral-800 truncate">
            Helpdesk Assistant
          </h1>
        </header>
        <main ref={mainRef} className="flex-1 overflow-hidden" role="main" tabIndex={-1}>
          <ReplyPanel />
        </main>
      </div>
    </ErrorBoundary>
  )
}
