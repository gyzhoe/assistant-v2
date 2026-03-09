import React, { useState, useEffect, useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { useBackendHealth } from '../hooks/useBackendHealth'
import { useBackendControl } from '../hooks/useBackendControl'
import { useLlmControl } from '../hooks/useLlmControl'
import { OnboardingCard } from './OnboardingCard'
import { ServiceRow } from './ServiceRow'
import { ThemeToggle } from './ThemeToggle'
import { GearIcon } from '../../shared/components/Icons'
import type { AppSettings } from '../../shared/types'

interface BackendControlProps {
  themeSetting: AppSettings['theme']
  resolvedTheme: 'light' | 'dark'
  onCycleTheme: () => void
}

const ONBOARDING_DISMISSED_KEY = 'onboardingDismissed'

export function BackendControl({ themeSetting, resolvedTheme, onCycleTheme }: BackendControlProps): React.ReactElement {
  const [collapsed, setCollapsed] = useState(false)
  const [onboardingDismissed, setOnboardingDismissed] = useState(true) // default true to avoid flash

  const ticketData = useSidebarStore((s) => s.ticketData)
  const isTicketPage = useSidebarStore((s) => s.isTicketPage)
  const modelConfirmed = useSidebarStore((s) => s.modelConfirmed)

  const health = useBackendHealth()

  const backend = useBackendControl({
    checkHealth: health.checkHealth,
    schedulePoll: health.schedulePoll,
    clearTimer: health.clearTimer,
    setStatus: health.setStatus,
    setLlmOk: health.setLlmOk,
    setVersion: health.setVersion,
    mountedRef: health.mountedRef,
    pollIntervalRef: health.pollIntervalRef,
  })

  const llm = useLlmControl({
    checkHealth: health.checkHealth,
    schedulePoll: health.schedulePoll,
    clearTimer: health.clearTimer,
    setLlmOk: health.setLlmOk,
    setVersion: health.setVersion,
    setNativeError: backend.setNativeError,
    mountedRef: health.mountedRef,
    timerRef: health.timerRef,
  })

  // Load onboarding dismissed state
  useEffect(() => {
    chrome.storage.local.get(ONBOARDING_DISMISSED_KEY, (result) => {
      if (health.mountedRef.current) {
        setOnboardingDismissed(result[ONBOARDING_DISMISSED_KEY] === true)
      }
    })
  // mountedRef is a stable ref - safe to omit
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Derived state
  const backendOk = health.status === 'online'
  const isCorsBlocked = health.status === 'cors_blocked'
  const modelOk = modelConfirmed
  const allServicesOk = backendOk && health.llmOk && modelOk

  // Auto-dismiss onboarding when all service checks pass
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
  // CORS blocked means backend is reachable - don't show onboarding.
  const showOnboarding =
    health.status === 'offline' && !health.llmOk && !onboardingDismissed

  // Readiness badges
  const readiness = [
    { label: 'Ticket detected', ok: Boolean(isTicketPage && ticketData) },
    { label: 'Backend connected', ok: backendOk },
    { label: 'LLM server ready', ok: health.llmOk },
    { label: 'Model selected', ok: modelOk },
  ]

  const allReady = readiness.every((r) => r.ok)

  const chipLabel =
    health.status === 'checking' || health.status === 'starting' ? 'Checking\u2026' :
    health.status === 'stopping' ? 'Stopping\u2026' :
    health.status === 'cors_blocked' ? 'CORS Blocked' :
    health.status === 'offline' ? 'Offline' :
    allReady ? 'Ready' : 'Attention'

  const chipClass =
    health.status === 'checking' || health.status === 'starting' || health.status === 'stopping' ? 'pending' :
    health.status === 'offline' || health.status === 'cors_blocked' ? 'error' :
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
              llmOk={health.llmOk}
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
          {health.status === 'online' && (
            <>
              <ServiceRow label="Backend" statusColor="ok" info={`v${health.version}`}>
                <button onClick={backend.handleStop} className="svc-btn danger" aria-label="Stop backend">Stop</button>
              </ServiceRow>
              <ServiceRow label="LLM Server" statusColor={health.llmOk ? 'ok' : 'error'}>
                {health.llmOk && llm.llmAction === 'idle' && !llm.confirmRestart && (
                  <>
                    <button
                      onClick={llm.requestConfirmRestart}
                      className="svc-btn success"
                      aria-label="Restart LLM server"
                    >
                      Restart
                    </button>
                    <button onClick={llm.handleStopLlm} className="svc-btn danger" aria-label="Stop LLM server">Stop</button>
                  </>
                )}
                {health.llmOk && llm.llmAction === 'idle' && llm.confirmRestart && (
                  <>
                    <span className="svc-action">Restart? (~30s downtime)</span>
                    <button onClick={llm.handleRestartLlm} className="svc-btn success" aria-label="Confirm restart">Confirm</button>
                    <button onClick={llm.cancelConfirm} className="svc-btn danger" aria-label="Cancel restart">Cancel</button>
                  </>
                )}
                {!health.llmOk && llm.llmAction === 'idle' && (
                  <button onClick={llm.handleStartLlm} className="svc-btn success" aria-label="Start LLM server">Start</button>
                )}
                {llm.llmAction === 'starting' && <span className="svc-action">Starting\u2026</span>}
                {llm.llmAction === 'stopping' && <span className="svc-action">Stopping\u2026</span>}
                {llm.llmAction === 'restarting' && <span className="svc-action">Restarting\u2026</span>}
              </ServiceRow>
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
          {health.status === 'offline' && (
            <div className="offline-controls">
              <button onClick={backend.handleStart} className="svc-btn success full-width" aria-label="Start backend">
                Start Backend
              </button>
              {backend.nativeError && (
                <p className="support-text error-text" role="alert">
                  {backend.nativeError.includes('native') || backend.nativeError.includes('Specified native')
                    ? 'Native messaging not set up. Start manually or run the registration script.'
                    : backend.nativeError}
                </p>
              )}
            </div>
          )}

          {/* --- Transitional --- */}
          {health.status === 'stopping' && <p className="support-text">Shutting down\u2026</p>}
          {health.status === 'starting' && <p className="support-text">{backend.startingDetail || 'Starting\u2026'}</p>}

          {/* --- LLM restart error (shown in any online state) --- */}
          {backend.nativeError && health.status === 'online' && (
            <p className="support-text error-text" role="alert">{backend.nativeError}</p>
          )}
        </div>
      )}
    </section>
  )
}
