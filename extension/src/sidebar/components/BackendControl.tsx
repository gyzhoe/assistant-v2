import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient, sendNativeCommand } from '../../lib/api-client'
import { isCorsProbablyBlocked } from '../../lib/cors-detect'
import { ThemeToggle } from './ThemeToggle'
import { GearIcon } from '../../shared/components/Icons'
import type { AppSettings } from '../../shared/types'

type BackendStatus = 'online' | 'offline' | 'cors_blocked' | 'checking' | 'stopping' | 'starting'

interface BackendControlProps {
  themeSetting: AppSettings['theme']
  resolvedTheme: 'light' | 'dark'
  onCycleTheme: () => void
}

const POLL_BASE_MS = 5000
const POLL_FAST_MS = 1500
const POLL_MAX_MS = 60000
const ONBOARDING_DISMISSED_KEY = 'onboardingDismissed'

/** Minimum delay after stop before allowing start, to ensure port is freed */
const STOP_SETTLE_MIN_MS = 2000

/** Maximum time to wait for the backend to confirm it's down after stop */
const STOP_CONFIRM_TIMEOUT_MS = 10000

/** Polling interval when confirming server is down after stop */
const STOP_CONFIRM_POLL_MS = 500

/** Maximum time to wait for LLM to come back after restart */
const RESTART_TIMEOUT_MS = 30000

/** Polling interval during LLM restart health checks */
const RESTART_POLL_MS = 2000

/** Exponential backoff for offline polling: 5s → 15s → 30s → 60s max */
function nextOfflinePollMs(currentMs: number): number {
  if (currentMs < 15000) return 15000
  if (currentMs < 30000) return 30000
  return POLL_MAX_MS
}

function OnboardingCard({
  backendOk,
  llmOk,
  modelOk,
  onDismiss,
}: {
  backendOk: boolean
  llmOk: boolean
  modelOk: boolean
  onDismiss: () => void
}) {
  const steps = [
    {
      label: 'Start LLM server',
      done: llmOk,
      hint: (
        <>
          Start the LLM server via the installer or manually.
        </>
      ),
    },
    {
      label: 'Download models',
      done: modelOk,
      hint: (
        <>
          Download models via Start Menu &rarr; Setup LLM Models.
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
  const [llmOk, setLlmOk] = useState(false)
  const [llmAction, setLlmAction] = useState<'idle' | 'starting' | 'stopping' | 'restarting'>('idle')
  const [version, setVersion] = useState('')
  const [nativeError, setNativeError] = useState('')
  const [startingDetail, setStartingDetail] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const [onboardingDismissed, setOnboardingDismissed] = useState(true) // default true to avoid flash
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  const actionInFlightRef = useRef(false)
  const pollIntervalRef = useRef<number>(POLL_BASE_MS)

  const ticketData = useSidebarStore((s) => s.ticketData)
  const isTicketPage = useSidebarStore((s) => s.isTicketPage)
  const modelConfirmed = useSidebarStore((s) => s.modelConfirmed)
  const setModelConfirmed = useSidebarStore((s) => s.setModelConfirmed)
  const setLlmReachable = useSidebarStore((s) => s.setLlmReachable)
  const setChromaDocCounts = useSidebarStore((s) => s.setChromaDocCounts)

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

  // Returns true if backend was reachable
  const checkHealth = useCallback(async (): Promise<boolean> => {
    try {
      const h = await apiClient.health()
      if (!mountedRef.current) return false
      setStatus('online')
      setLlmOk(h.llm_reachable)
      setLlmReachable(h.llm_reachable)
      setChromaDocCounts(h.chroma_doc_counts ?? {})
      setVersion(h.version)
      if (h.llm_reachable) setLlmAction('idle')
      return true
    } catch {
      if (!mountedRef.current) return false
      // Distinguish CORS rejection from genuine offline
      const corsBlocked = await isCorsProbablyBlocked()
      if (!mountedRef.current) return false
      setStatus(corsBlocked ? 'cors_blocked' : 'offline')
      setLlmOk(false)
      setLlmReachable(false)
      setModelConfirmed(false)
      setVersion('')
      return false
    }
  }, [setLlmReachable, setChromaDocCounts, setModelConfirmed])

  const schedulePoll = useCallback((delayMs?: number) => {
    clearTimer()
    // Use provided delay or current interval, then advance backoff if offline
    const interval = delayMs ?? pollIntervalRef.current
    timerRef.current = setTimeout(() => {
      if (mountedRef.current) {
        checkHealth().then((online) => {
          if (!mountedRef.current) return
          if (online) {
            // Reconnected — reset backoff
            pollIntervalRef.current = POLL_BASE_MS
          } else {
            // Still offline — advance backoff for next cycle
            pollIntervalRef.current = nextOfflinePollMs(pollIntervalRef.current)
          }
          schedulePoll()
        }).catch(() => {})
      }
    }, interval)
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

  // Pause polling while the sidebar is hidden (tab not visible)
  useEffect(() => {
    const handler = () => {
      if (!mountedRef.current) return
      if (document.visibilityState === 'hidden') {
        clearTimer()
      } else {
        // Resume with an immediate health check and reset backoff
        checkHealth().then((online) => {
          if (!mountedRef.current) return
          pollIntervalRef.current = online ? POLL_BASE_MS : nextOfflinePollMs(POLL_BASE_MS)
          schedulePoll()
        }).catch(() => {})
      }
    }
    document.addEventListener('visibilitychange', handler)
    return () => document.removeEventListener('visibilitychange', handler)
  }, [checkHealth, schedulePoll])

  // Auto-dismiss onboarding when all service checks pass
  const backendOk = status === 'online'
  const isCorsBlocked = status === 'cors_blocked'
  const modelOk = modelConfirmed
  const allServicesOk = backendOk && llmOk && modelOk

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
  // CORS blocked means backend is reachable — don't show onboarding.
  const showOnboarding =
    status === 'offline' && !llmOk && !onboardingDismissed

  // --- Wait for server to fully stop (poll health until connection error) ---
  const waitForServerDown = useCallback((): Promise<void> => {
    return new Promise((resolve) => {
      const startTime = Date.now()

      const check = () => {
        if (!mountedRef.current) {
          resolve()
          return
        }
        if (Date.now() - startTime > STOP_CONFIRM_TIMEOUT_MS) {
          resolve()
          return
        }
        apiClient.health().then(() => {
          // Still responding — keep polling
          setTimeout(check, STOP_CONFIRM_POLL_MS)
        }).catch(() => {
          // Connection error — server is down
          resolve()
        })
      }

      check()
    })
  }, [])

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

    // Wait for server to confirm it's fully down, with a minimum settle time
    const settlePromise = new Promise<void>((r) => setTimeout(r, STOP_SETTLE_MIN_MS))
    const downPromise = waitForServerDown()
    await Promise.all([settlePromise, downPromise])

    if (!mountedRef.current) return
    setStatus('offline')
    setLlmOk(false)
    setModelConfirmed(false)
    setVersion('')
    pollIntervalRef.current = POLL_BASE_MS
    actionInFlightRef.current = false
    schedulePoll()
  }

  const handleStartBackend = async () => {
    if (actionInFlightRef.current) return
    actionInFlightRef.current = true
    setStatus('starting')
    setNativeError('')
    setStartingDetail('Connecting to native host\u2026')
    const resp = await sendNativeCommand('start_backend')
    if (!mountedRef.current) return
    if (!resp.ok) {
      setNativeError(resp.error ?? 'Native messaging unavailable')
      setStatus('offline')
      setStartingDetail('')
      actionInFlightRef.current = false
      return
    }
    // Show phase-specific status based on native host response
    if (resp.llm_started) {
      setStartingDetail('Starting LLM server\u2026')
      await new Promise((r) => setTimeout(r, 1500))
      if (!mountedRef.current) return
    }
    setStartingDetail('Starting backend server\u2026')
    // Poll aggressively until backend responds (up to 15s)
    clearTimer()
    let attempts = 0
    const maxAttempts = 10
    const pollStartup = async () => {
      if (!mountedRef.current) return
      attempts++
      const online = await checkHealth()
      if (online) {
        setStartingDetail('')
        actionInFlightRef.current = false
        schedulePoll()
        return
      }
      // Keep 'starting' status during startup polling — checkHealth sets 'offline'
      // on failure which would briefly flash the Start button before the next attempt.
      if (attempts < maxAttempts) {
        setStatus('starting')
        setStartingDetail(attempts >= 3 ? 'Waiting for backend to respond\u2026' : 'Starting backend server\u2026')
        setTimeout(pollStartup, POLL_FAST_MS)
      } else {
        setStartingDetail('')
        actionInFlightRef.current = false
        schedulePoll()
      }
    }
    setTimeout(pollStartup, 2000)
  }

  // --- LLM server controls ---

  const handleStartLlm = async () => {
    setLlmAction('starting')
    try {
      await apiClient.llmStart()
    } catch {
      const resp = await sendNativeCommand('start_llm')
      if (!resp.ok) {
        setNativeError(resp.error ?? 'Failed to start LLM server')
        setLlmAction('idle')
        return
      }
    }
    clearTimer()
    setTimeout(() => {
      if (mountedRef.current) checkHealth().finally(() => schedulePoll())
    }, 3000)
  }

  const handleStopLlm = async () => {
    setLlmAction('stopping')
    try {
      await apiClient.llmStop()
    } catch {
      // Backend unreachable — fall back to native messaging (OS-level kill)
      const resp = await sendNativeCommand('stop_llm')
      if (!resp.ok) {
        setNativeError(resp.error ?? 'Failed to stop LLM server')
        setLlmAction('idle')
        return
      }
    }
    clearTimer()
    setTimeout(() => {
      if (mountedRef.current) {
        setLlmAction('idle')
        checkHealth().finally(() => schedulePoll())
      }
    }, POLL_FAST_MS)
  }

  const handleRestartLlm = async () => {
    if (llmAction !== 'idle') return
    setLlmAction('restarting')
    clearTimer()

    try {
      await apiClient.llmRestart()
    } catch {
      // If the endpoint fails, fall back to stop+start
      setLlmAction('idle')
      setNativeError('Failed to restart LLM server. Try stopping and starting manually.')
      schedulePoll()
      return
    }

    // Poll health until LLM comes back or timeout
    const startTime = Date.now()
    const pollRestart = () => {
      if (!mountedRef.current) return
      if (Date.now() - startTime > RESTART_TIMEOUT_MS) {
        setLlmAction('idle')
        setNativeError('LLM restart timed out — server may still be loading')
        schedulePoll()
        return
      }

      apiClient.health().then((h) => {
        if (!mountedRef.current) return
        setLlmOk(h.llm_reachable)
        setLlmReachable(h.llm_reachable)
        setVersion(h.version)
        if (h.llm_reachable) {
          setLlmAction('idle')
          setNativeError('')
          schedulePoll()
        } else {
          timerRef.current = setTimeout(pollRestart, RESTART_POLL_MS)
        }
      }).catch(() => {
        if (mountedRef.current) {
          timerRef.current = setTimeout(pollRestart, RESTART_POLL_MS)
        }
      })
    }

    // Give the server a moment to begin restarting before polling
    timerRef.current = setTimeout(pollRestart, RESTART_POLL_MS)
  }

  // --- Readiness badges ---

  const readiness = [
    { label: 'Ticket detected', ok: Boolean(isTicketPage && ticketData) },
    { label: 'Backend connected', ok: backendOk },
    { label: 'LLM server ready', ok: llmOk },
    { label: 'Model selected', ok: modelOk },
  ]

  const allReady = readiness.every((r) => r.ok)

  const chipLabel =
    status === 'checking' || status === 'starting' ? 'Checking\u2026' :
    status === 'stopping' ? 'Stopping\u2026' :
    status === 'cors_blocked' ? 'CORS Blocked' :
    status === 'offline' ? 'Offline' :
    allReady ? 'Ready' : 'Attention'

  const chipClass =
    status === 'checking' || status === 'starting' || status === 'stopping' ? 'pending' :
    status === 'offline' || status === 'cors_blocked' ? 'error' :
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
          className="settings-btn"
          onClick={() => chrome.runtime.openOptionsPage()}
          aria-label="Open settings"
          title="Settings"
        >
          <GearIcon />
        </button>
      </div>

      {!collapsed && (
        <div id="status-panel-body" className="collapsible-body">
          {/* --- Onboarding card (shown when all services are down) --- */}
          {showOnboarding && (
            <OnboardingCard
              backendOk={backendOk}
              llmOk={llmOk}
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
                <span className={`service-indicator ${llmOk ? 'ok' : 'error'}`} />
                <span className="service-label">LLM Server</span>
                {llmOk && llmAction === 'idle' && (
                  <>
                    <button onClick={handleRestartLlm} className="svc-btn success" aria-label="Restart LLM server">Restart</button>
                    <button onClick={handleStopLlm} className="svc-btn danger" aria-label="Stop LLM server">Stop</button>
                  </>
                )}
                {!llmOk && llmAction === 'idle' && (
                  <button onClick={handleStartLlm} className="svc-btn success" aria-label="Start LLM server">Start</button>
                )}
                {llmAction === 'starting' && <span className="svc-action">Starting…</span>}
                {llmAction === 'stopping' && <span className="svc-action">Stopping…</span>}
                {llmAction === 'restarting' && <span className="svc-action">Restarting…</span>}
              </div>
            </>
          )}

          {/* --- CORS blocked --- */}
          {isCorsBlocked && (
            <div className="offline-controls">
              <p className="support-text error-text" role="alert">
                Connection blocked — the backend is running but CORS is rejecting requests.
                Check that your extension ID matches the allowed origin in the backend configuration.
              </p>
              <button
                onClick={() => chrome.runtime.openOptionsPage()}
                className="svc-btn full-width"
                aria-label="Open settings"
              >
                Open Settings
              </button>
            </div>
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
          {status === 'starting' && <p className="support-text">{startingDetail || 'Starting\u2026'}</p>}

          {/* --- LLM restart error (shown in any online state) --- */}
          {nativeError && status === 'online' && (
            <p className="support-text error-text" role="alert">{nativeError}</p>
          )}
        </div>
      )}
    </section>
  )
}
