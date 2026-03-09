import { useState, useRef, useCallback, type MutableRefObject } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient, sendNativeCommand } from '../../lib/api-client'
import type { BackendStatus } from './useBackendHealth'

/** Minimum delay after stop before allowing start, to ensure port is freed */
const STOP_SETTLE_MIN_MS = 2000

/** Maximum time to wait for the backend to confirm it's down after stop */
const STOP_CONFIRM_TIMEOUT_MS = 10000

/** Polling interval when confirming server is down after stop */
const STOP_CONFIRM_POLL_MS = 500

/** Polling interval during startup health checks */
const POLL_FAST_MS = 1500

/** Base polling interval (for reset after action completes) */
const POLL_BASE_MS = 5000

interface UseBackendControlParams {
  checkHealth: () => Promise<boolean>
  schedulePoll: (delayMs?: number) => void
  clearTimer: () => void
  setStatus: (status: BackendStatus) => void
  setLlmOk: (ok: boolean) => void
  setVersion: (version: string) => void
  mountedRef: MutableRefObject<boolean>
  pollIntervalRef: MutableRefObject<number>
}

export interface UseBackendControlReturn {
  handleStart: () => Promise<void>
  handleStop: () => Promise<void>
  nativeError: string
  startingDetail: string
  setNativeError: (err: string) => void
}

export function useBackendControl({
  checkHealth,
  schedulePoll,
  clearTimer,
  setStatus,
  setLlmOk,
  setVersion,
  mountedRef,
  pollIntervalRef,
}: UseBackendControlParams): UseBackendControlReturn {
  const [nativeError, setNativeError] = useState('')
  const [startingDetail, setStartingDetail] = useState('')
  const actionInFlightRef = useRef(false)

  const setModelConfirmed = useSidebarStore((s) => s.setModelConfirmed)

  /** Wait for server to fully stop (poll health until connection error) */
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
          // Still responding - keep polling
          setTimeout(check, STOP_CONFIRM_POLL_MS)
        }).catch(() => {
          // Connection error - server is down
          resolve()
        })
      }

      check()
    })
  }, [mountedRef])

  const handleStop = useCallback(async () => {
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
  }, [schedulePoll, clearTimer, setStatus, setLlmOk, setVersion, mountedRef, pollIntervalRef, setModelConfirmed, waitForServerDown])

  const handleStart = useCallback(async () => {
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
      // Keep 'starting' status during startup polling - checkHealth sets 'offline'
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
  }, [checkHealth, schedulePoll, clearTimer, setStatus, mountedRef])

  return {
    handleStart,
    handleStop,
    nativeError,
    startingDetail,
    setNativeError,
  }
}
