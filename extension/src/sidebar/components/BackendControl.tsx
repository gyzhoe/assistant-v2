import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient, sendNativeCommand } from '../../lib/api-client'
import { ThemeToggle } from './ThemeToggle'
import { DEFAULT_MODEL } from '../../shared/constants'
import type { AppSettings } from '../../shared/types'

type BackendStatus = 'online' | 'offline' | 'checking' | 'stopping' | 'starting'

interface BackendControlProps {
  themeSetting: AppSettings['theme']
  resolvedTheme: 'light' | 'dark'
  onCycleTheme: () => void
}

const POLL_INTERVAL_MS = 5000
const FAST_POLL_MS = 1500
const ONBOARDING_DISMISSED_KEY = 'onboardingDismissed'

function OnboardingCard({
  backendOk,
  ollamaOk,
  modelOk,
  onDismiss,
}: {
  backendOk: boolean
  ollamaOk: boolean
  modelOk: boolean
  onDismiss: () => void
}) {
  const steps = [
    {
      label: 'Install Ollama',
      done: ollamaOk,
      hint: (
        <>
          Download from{' '}
          <a href="https://ollama.com" target="_blank" rel="noopener noreferrer">
            ollama.com
          </a>
          , then run it.
        </>
      ),
    },
    {
      label: 'Pull a model',
      done: modelOk,
      hint: (
        <>
          Run <code>ollama pull {DEFAULT_MODEL}</code> in your terminal.
        </>
      ),
    },
    {
      label: 'Start the backend',
      done: backendOk,
      hint: <>Start the AI Helpdesk backend server (port 8765).</>,
    },
  ]

  return (
    <div className="onboarding-card" role="region" aria-label="Getting started">
      <h3 className="onboarding-title">Getting Started</h3>
      <p className="onboarding-subtitle">
        Complete these steps to start using the AI assistant.
      </p>
      <div className="onboarding-steps">
        {steps.map((step) => (
          <div key={step.label} className="onboarding-step">
            <span className={`onboarding-step-indicator ${step.done ? 'done' : 'pending'}`}>
              {step.done ? '\u2713' : '\u00B7'}
            </span>
            <div className="onboarding-step-body">
              <span className="onboarding-step-label">{step.label}</span>
              {!step.done && <span className="onboarding-step-hint">{step.hint}</span>}
            </div>
          </div>
        ))}
      </div>
      <button className="onboarding-dismiss" onClick={onDismiss} type="button">
        Dismiss
      </button>
    </div>
  )
}

export function BackendControl({ themeSetting, resolvedTheme, onCycleTheme }: BackendControlProps): React.ReactElement {
  const [status, setStatus] = useState<BackendStatus>('checking')
  const [ollamaOk, setOllamaOk] = useState(false)
  const [ollamaAction, setOllamaAction] = useState<'idle' | 'starting' | 'stopping'>('idle')
  const [version, setVersion] = useState('')
  const [nativeError, setNativeError] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const [onboardingDismissed, setOnboardingDismissed] = useState(true) // default true to avoid flash
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  const actionInFlightRef = useRef(false)

  const ticketData = useSidebarStore((s) => s.ticketData)
  const isTicketPage = useSidebarStore((s) => s.isTicketPage)
  const selectedModel = useSidebarStore((s) => s.selectedModel)

  // Load onboarding dismissed state
  useEffect(() => {
    chrome.storage.local.get(ONBOARDING_DISMISSED_KEY, (result) => {
      if (mountedRef.current) {
        setOnboardingDismissed(result[ONBOARDING_DISMISSED_KEY] === true)
      }
    })
  }, [])

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

  // Auto-dismiss onboarding when all service checks pass
  const backendOk = status === 'online'
  const modelOk = selectedModel.length > 0
  const allServicesOk = backendOk && ollamaOk && modelOk

  useEffect(() => {
    if (allServicesOk && !onboardingDismissed) {
      setOnboardingDismissed(true)
      chrome.storage.local.set({ [ONBOARDING_DISMISSED_KEY]: true })
    }
  }, [allServicesOk, onboardingDismissed])

  const handleDismissOnboarding = useCallback(() => {
    setOnboardingDismissed(true)
    chrome.storage.local.set({ [ONBOARDING_DISMISSED_KEY]: true })
  }, [])

  // Show onboarding when ALL service checks fail and user hasn't dismissed.
  // Don't show during initial 'checking' phase to avoid a flash.
  const showOnboarding =
    status === 'offline' && !ollamaOk && !onboardingDismissed

  // --- Backend controls ---

  const handleStopBackend = async () => {
    if (actionInFlightRef.current) return
    actionInFlightRef.current = true
    setStatus('stopping')
    // Native messaging (OS-level kill) first, HTTP fallback
    const resp = await sendNativeCommand('stop_backend')
    if (!resp.ok) {
      apiClient.shutdown().catch(() => {})
    }
    clearTimer()
    // Go straight to offline after a brief visual pause
    setTimeout(() => {
      if (!mountedRef.current) return
      setStatus('offline')
      setOllamaOk(false)
      setVersion('')
      actionInFlightRef.current = false
      schedulePoll()
    }, 800)
  }

  const handleStartBackend = async () => {
    if (actionInFlightRef.current) return
    actionInFlightRef.current = true
    setStatus('starting')
    setNativeError('')
    const resp = await sendNativeCommand('start_backend')
    if (!mountedRef.current) return
    if (!resp.ok) {
      setNativeError(resp.error ?? 'Native messaging unavailable')
      setStatus('offline')
      actionInFlightRef.current = false
      return
    }
    clearTimer()
    setTimeout(() => {
      if (mountedRef.current) {
        actionInFlightRef.current = false
        checkHealth().finally(() => schedulePoll())
      }
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
    // Native messaging (OS-level kill) first, HTTP fallback
    const resp = await sendNativeCommand('stop_ollama')
    if (!resp.ok) {
      try { await apiClient.ollamaStop() } catch { /* ignore */ }
    }
    clearTimer()
    setTimeout(() => {
      if (mountedRef.current) {
        setOllamaAction('idle')
        checkHealth().finally(() => schedulePoll())
      }
    }, FAST_POLL_MS)
  }

  // --- Readiness badges ---

  const readiness = [
    { label: 'Ticket detected', ok: Boolean(isTicketPage && ticketData) },
    { label: 'Backend connected', ok: backendOk },
    { label: 'Ollama ready', ok: ollamaOk },
    { label: 'Model selected', ok: modelOk },
  ]

  const allReady = readiness.every((r) => r.ok)

  const chipLabel =
    status === 'checking' || status === 'starting' ? 'Checking\u2026' :
    status === 'stopping' ? 'Stopping\u2026' :
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
          <span className="heading-right">
            <span className={`status-chip ${chipClass}`}>{chipLabel}</span>
            <span className={`chevron ${collapsed ? '' : 'open'}`} aria-hidden="true" />
          </span>
        </button>
        <ThemeToggle
          theme={themeSetting}
          resolvedTheme={resolvedTheme}
          onCycle={onCycleTheme}
        />
        <button
          type="button"
          className="theme-toggle"
          onClick={() => chrome.runtime.openOptionsPage()}
          aria-label="Open settings"
          title="Settings"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="8" cy="8" r="2" />
            <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.05 3.05l1.06 1.06M11.89 11.89l1.06 1.06M3.05 12.95l1.06-1.06M11.89 4.11l1.06-1.06" />
          </svg>
        </button>
      </div>

      {!collapsed && (
        <div id="status-panel-body" className="collapsible-body">
          {/* --- Onboarding card (shown when all services are down) --- */}
          {showOnboarding && (
            <OnboardingCard
              backendOk={backendOk}
              ollamaOk={ollamaOk}
              modelOk={modelOk}
              onDismiss={handleDismissOnboarding}
            />
          )}

          {/* --- Readiness badges --- */}
          {!showOnboarding && (
            <div className="badge-grid">
              {readiness.map((r) => (
                <span key={r.label} className={`badge${r.ok ? ' ok' : ''}`}>
                  {r.ok ? '\u2713' : '\u2022'} {r.label}
                </span>
              ))}
            </div>
          )}

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
