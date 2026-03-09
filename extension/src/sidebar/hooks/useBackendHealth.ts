import { useState, useEffect, useRef, useCallback, type MutableRefObject } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient } from '../../lib/api-client'
import { isCorsProbablyBlocked } from '../../lib/cors-detect'

export type BackendStatus = 'online' | 'offline' | 'cors_blocked' | 'checking' | 'stopping' | 'starting'

const POLL_BASE_MS = 5000
const POLL_MAX_MS = 60000

/** Exponential backoff for offline polling: 5s -> 15s -> 30s -> 60s max */
function nextOfflinePollMs(currentMs: number): number {
  if (currentMs < 15000) return 15000
  if (currentMs < 30000) return 30000
  return POLL_MAX_MS
}

export interface UseBackendHealthReturn {
  status: BackendStatus
  version: string
  llmOk: boolean
  setStatus: (status: BackendStatus) => void
  setLlmOk: (ok: boolean) => void
  setVersion: (version: string) => void
  checkHealth: () => Promise<boolean>
  schedulePoll: (delayMs?: number) => void
  clearTimer: () => void
  mountedRef: MutableRefObject<boolean>
  timerRef: MutableRefObject<ReturnType<typeof setTimeout> | null>
  pollIntervalRef: MutableRefObject<number>
}

export function useBackendHealth(): UseBackendHealthReturn {
  const [status, setStatus] = useState<BackendStatus>('checking')
  const [llmOk, setLlmOk] = useState(false)
  const [version, setVersion] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  const pollIntervalRef = useRef<number>(POLL_BASE_MS)

  const setLlmReachable = useSidebarStore((s) => s.setLlmReachable)
  const setChromaDocCounts = useSidebarStore((s) => s.setChromaDocCounts)
  const setModelConfirmed = useSidebarStore((s) => s.setModelConfirmed)

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

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
            // Reconnected - reset backoff
            pollIntervalRef.current = POLL_BASE_MS
          } else {
            // Still offline - advance backoff for next cycle
            pollIntervalRef.current = nextOfflinePollMs(pollIntervalRef.current)
          }
          schedulePoll()
        }).catch(() => {})
      }
    }, interval)
  }, [checkHealth, clearTimer])

  // Initial health check + start polling
  useEffect(() => {
    mountedRef.current = true
    checkHealth().finally(() => {
      if (mountedRef.current) schedulePoll()
    })
    return () => {
      mountedRef.current = false
      clearTimer()
    }
  }, [checkHealth, schedulePoll, clearTimer])

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
  }, [checkHealth, schedulePoll, clearTimer])

  return {
    status,
    version,
    llmOk,
    setStatus,
    setLlmOk,
    setVersion,
    checkHealth,
    schedulePoll,
    clearTimer,
    mountedRef,
    timerRef,
    pollIntervalRef,
  }
}
