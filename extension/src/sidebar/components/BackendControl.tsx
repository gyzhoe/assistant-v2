import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient, sendNativeCommand } from '../../lib/api-client'
import { ThemeToggle } from './ThemeToggle'
import type { AppSettings } from '../../shared/types'

type BackendStatus = 'online' | 'offline' | 'checking' | 'stopping' | 'starting'

interface BackendControlProps {
  themeSetting: AppSettings['theme']
  resolvedTheme: 'light' | 'dark'
  onCycleTheme: () => void
}

const POLL_INTERVAL_MS = 5000
const FAST_POLL_MS = 1500

export function BackendControl({ themeSetting, resolvedTheme, onCycleTheme }: BackendControlProps): React.ReactElement {
  const [status, setStatus] = useState<BackendStatus>('checking')
  const [ollamaOk, setOllamaOk] = useState(false)
  const [ollamaAction, setOllamaAction] = useState<'idle' | 'starting' | 'stopping'>('idle')
  const [version, setVersion] = useState('')
  const [nativeError, setNativeError] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const ticketData = useSidebarStore((s) => s.ticketData)
  const isTicketPage = useSidebarStore((s) => s.isTicketPage)
  const selectedModel = useSidebarStore((s) => s.selectedModel)

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  const checkHealth = useCallback(async () => {
    try {
      const h = await apiClient.health()
      if (!mountedRef.current) return
      setStatus('online')
      setOllamaOk(h.ollama_reachable)
      setVersion(h.version)
      if (h.ollama_reachable) setOllamaAction('idle')
    } catch {
      if (!mountedRef.current) return
      setStatus('offline')
      setOllamaOk(false)
      setVersion('')
    }
  }, [])

  const schedulePoll = useCallback((delayMs: number = POLL_INTERVAL_MS) => {
    clearTimer()
    timerRef.current = setTimeout(() => {
      if (mountedRef.current) {
        checkHealth().finally(() => {
          if (mountedRef.current) schedulePoll()
        })
      }
    }, delayMs)
  }, [checkHealth])

  useEffect(() => {
    mountedRef.current = true
    checkHealth().finally(() => {
      if (mountedRef.current) schedulePoll()
    })
    return () => {
      mountedRef.current = false
      clearTimer()
    }
  }, [checkHealth, schedulePoll])

  // --- Backend controls ---

  const handleStopBackend = () => {
    setStatus('stopping')
    // Fire-and-forget — don't await; server may die before responding
    apiClient.shutdown().catch(() => {})
    clearTimer()
    // Go straight to offline after a brief visual pause
    setTimeout(() => {
      if (!mountedRef.current) return
      setStatus('offline')
      setOllamaOk(false)
      setVersion('')
      schedulePoll()
    }, 800)
  }

  const handleStartBackend = async () => {
    setStatus('starting')
    setNativeError('')
    const resp = await sendNativeCommand('start_backend')
    if (!mountedRef.current) return
    if (!resp.ok) {
      setNativeError(resp.error ?? 'Native messaging unavailable')
      setStatus('offline')
      return
    }
    clearTimer()
    setTimeout(() => {
      if (mountedRef.current) checkHealth().finally(() => schedulePoll())
    }, 3000)
  }

  // --- Ollama controls ---

  const handleStartOllama = async () => {
    setOllamaAction('starting')
    try {
      await apiClient.ollamaStart()
    } catch {
      const resp = await sendNativeCommand('start_ollama')
      if (!resp.ok) {
        setNativeError(resp.error ?? 'Failed to start Ollama')
        setOllamaAction('idle')
        return
      }
    }
    clearTimer()
    setTimeout(() => {
      if (mountedRef.current) checkHealth().finally(() => schedulePoll())
    }, 3000)
  }

  const handleStopOllama = async () => {
    setOllamaAction('stopping')
    try { await apiClient.ollamaStop() } catch { /* ignore */ }
    clearTimer()
    setTimeout(() => {
      if (mountedRef.current) {
        setOllamaAction('idle')
        checkHealth().finally(() => schedulePoll())
      }
    }, FAST_POLL_MS)
  }

  // --- Readiness badges ---

  const readiness = useMemo(() => [
    { label: 'Ticket detected', ok: Boolean(isTicketPage && ticketData) },
    { label: 'Backend connected', ok: status === 'online' },
    { label: 'Ollama ready', ok: ollamaOk },
    { label: 'Model selected', ok: selectedModel.length > 0 },
  ], [isTicketPage, ticketData, status, ollamaOk, selectedModel])

  const allReady = readiness.every((r) => r.ok)

  const chipLabel =
    status === 'checking' || status === 'starting' ? 'Checking…' :
    status === 'stopping' ? 'Stopping…' :
    status === 'offline' ? 'Offline' :
    allReady ? 'Ready' : 'Attention'

  const chipClass =
    status === 'checking' || status === 'starting' || status === 'stopping' ? 'pending' :
    status === 'offline' ? 'error' :
    allReady ? 'ok' : 'pending'

  return (
    <section className="panel" aria-label="Status and services">
      <div className="section-heading-row">
        <button
          className="collapsible-trigger"
          onClick={() => setCollapsed((c) => !c)}
          aria-expanded={!collapsed}
          aria-controls="status-panel-body"
        >
          <h2 className="section-heading">Status</h2>
        </button>
        <ThemeToggle
          theme={themeSetting}
          resolvedTheme={resolvedTheme}
          onCycle={onCycleTheme}
        />
        <div
          className="heading-right"
          onClick={() => setCollapsed((c) => !c)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setCollapsed((c) => !c) }}
          aria-label={collapsed ? 'Expand status panel' : 'Collapse status panel'}
        >
          <span className={`status-chip ${chipClass}`}>{chipLabel}</span>
          <span className={`chevron ${collapsed ? '' : 'open'}`} aria-hidden="true" />
        </div>
      </div>

      {!collapsed && (
        <div id="status-panel-body" className="collapsible-body">
          {/* --- Readiness badges --- */}
          <div className="badge-grid">
            {readiness.map((r) => (
              <span key={r.label} className={`badge${r.ok ? ' ok' : ''}`}>
                {r.ok ? '\u2713' : '\u2022'} {r.label}
              </span>
            ))}
          </div>

          {/* --- Services (online) --- */}
          {status === 'online' && (
            <>
              <div className="service-row">
                <span className="service-indicator ok" />
                <span className="service-label">Backend <span className="backend-info">v{version}</span></span>
                <button onClick={handleStopBackend} className="svc-btn danger" aria-label="Stop backend">Stop</button>
              </div>
              <div className="service-row">
                <span className={`service-indicator ${ollamaOk ? 'ok' : 'error'}`} />
                <span className="service-label">Ollama</span>
                {ollamaOk && ollamaAction === 'idle' && (
                  <button onClick={handleStopOllama} className="svc-btn danger" aria-label="Stop Ollama">Stop</button>
                )}
                {!ollamaOk && ollamaAction === 'idle' && (
                  <button onClick={handleStartOllama} className="svc-btn success" aria-label="Start Ollama">Start</button>
                )}
                {ollamaAction === 'starting' && <span className="svc-action">Starting…</span>}
                {ollamaAction === 'stopping' && <span className="svc-action">Stopping…</span>}
              </div>
            </>
          )}

          {/* --- Offline --- */}
          {status === 'offline' && (
            <div className="offline-controls">
              <button onClick={handleStartBackend} className="svc-btn success full-width" aria-label="Start backend">
                Start Backend
              </button>
              {nativeError && (
                <p className="support-text error-text" role="alert">
                  {nativeError.includes('native') || nativeError.includes('Specified native')
                    ? 'Native messaging not set up. Start manually or run the registration script.'
                    : nativeError}
                </p>
              )}
            </div>
          )}

          {/* --- Transitional --- */}
          {status === 'stopping' && <p className="support-text">Shutting down…</p>}
          {status === 'starting' && <p className="support-text">Starting backend server…</p>}
        </div>
      )}
    </section>
  )
}
