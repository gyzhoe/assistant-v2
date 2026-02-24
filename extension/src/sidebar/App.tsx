import React, { useEffect, useRef } from 'react'
import { BackendControl } from './components/BackendControl'
import { ReplyPanel } from './components/ReplyPanel'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ThemeToggle } from './components/ThemeToggle'
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
        <header className="app-header" role="banner">
          <div className="brand-mark" aria-hidden="true">
            AI
          </div>
          <div className="brand-copy">
            <h1>Helpdesk Assistant</h1>
            <p>AI-powered ticket responses</p>
          </div>
          <ThemeToggle
            theme={themeSetting}
            resolvedTheme={resolvedTheme}
            onCycle={cycleTheme}
          />
        </header>
        <main ref={mainRef} className="app-main" role="main" tabIndex={-1}>
          <BackendControl />
          <ReplyPanel />
        </main>
      </ErrorBoundary>
    </div>
  )
}
