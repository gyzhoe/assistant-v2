import { useState, useRef, useCallback, type MutableRefObject } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient, sendNativeCommand } from '../../lib/api-client'

/** Polling interval for fast health checks after LLM actions */
const POLL_FAST_MS = 1500

/** Maximum time to wait for LLM to come back after restart */
const RESTART_TIMEOUT_MS = 30000

/** Polling interval during LLM restart health checks */
const RESTART_POLL_MS = 2000

interface UseLlmControlParams {
  checkHealth: () => Promise<boolean>
  schedulePoll: (delayMs?: number) => void
  clearTimer: () => void
  setLlmOk: (ok: boolean) => void
  setVersion: (version: string) => void
  setNativeError: (err: string) => void
  mountedRef: MutableRefObject<boolean>
  timerRef: MutableRefObject<ReturnType<typeof setTimeout> | null>
}

export interface UseLlmControlReturn {
  llmAction: 'idle' | 'starting' | 'stopping' | 'restarting'
  confirmRestart: boolean
  handleStartLlm: () => Promise<void>
  handleStopLlm: () => Promise<void>
  handleRestartLlm: () => Promise<void>
  cancelConfirm: () => void
  requestConfirmRestart: () => void
}

export function useLlmControl({
  checkHealth,
  schedulePoll,
  clearTimer,
  setLlmOk,
  setVersion,
  setNativeError,
  mountedRef,
  timerRef,
}: UseLlmControlParams): UseLlmControlReturn {
  const [llmAction, setLlmAction] = useState<'idle' | 'starting' | 'stopping' | 'restarting'>('idle')
  const [confirmRestart, setConfirmRestart] = useState(false)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const setLlmReachable = useSidebarStore((s) => s.setLlmReachable)

  const handleStartLlm = useCallback(async () => {
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
  }, [checkHealth, schedulePoll, clearTimer, mountedRef, setNativeError])

  const handleStopLlm = useCallback(async () => {
    setLlmAction('stopping')
    try {
      await apiClient.llmStop()
    } catch {
      // Backend unreachable - fall back to native messaging (OS-level kill)
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
  }, [checkHealth, schedulePoll, clearTimer, mountedRef, setNativeError])

  const handleRestartLlm = useCallback(async () => {
    if (llmAction !== 'idle') return
    setLlmAction('restarting')
    setConfirmRestart(false)
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
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
        setNativeError('LLM restart timed out \u2014 server may still be loading')
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
  }, [llmAction, schedulePoll, clearTimer, setLlmOk, setVersion, mountedRef, timerRef, setLlmReachable, setNativeError])

  const requestConfirmRestart = useCallback(() => {
    setConfirmRestart(true)
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
    confirmTimerRef.current = setTimeout(() => setConfirmRestart(false), 5000)
  }, [])

  const cancelConfirm = useCallback(() => {
    setConfirmRestart(false)
  }, [])

  return {
    llmAction,
    confirmRestart,
    handleStartLlm,
    handleStopLlm,
    handleRestartLlm,
    cancelConfirm,
    requestConfirmRestart,
  }
}
