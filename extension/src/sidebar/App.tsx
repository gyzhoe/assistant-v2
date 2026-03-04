import React, { useEffect, useRef } from 'react'
import { BackendControl } from './components/BackendControl'
import { KnowledgePanel } from './components/KnowledgePanel'
import { ReplyPanel } from './components/ReplyPanel'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastContainer } from '@/shared/components/Toast'
import { useTheme } from './hooks/useTheme'

export default function App(): React.ReactElement {
  const mainRef = useRef<HTMLElement>(null)
  const { resolvedTheme, themeSetting, cycleTheme } = useTheme()

  useEffect(() => {
    mainRef.current?.focus()
  }, [])

  return (
    <div className="app-shell" data-theme={resolvedTheme}>
      <ErrorBoundary>
        <main ref={mainRef} className="app-main" role="main" aria-label="AI Helpdesk sidebar" tabIndex={-1}>
          <BackendControl
            themeSetting={themeSetting}
            resolvedTheme={resolvedTheme}
            onCycleTheme={cycleTheme}
          />
          <KnowledgePanel />
          <ReplyPanel />
        </main>
      </ErrorBoundary>
      <ToastContainer />
    </div>
  )
}
