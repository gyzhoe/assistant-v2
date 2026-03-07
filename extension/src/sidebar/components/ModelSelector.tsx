import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient, ApiError } from '../../lib/api-client'
import { parseErrorDetail } from '../../lib/error-utils'
import { DEFAULT_MODEL, debugError } from '../../shared/constants'

const MODEL_DESCRIPTIONS: Record<string, string> = {
  'qwen3.5:9b': '9B — fast, excellent quality',
  'qwen3:14b': '14B — slower, better quality + language control',
}

/** Polling interval while waiting for model switch to complete */
const SWITCH_POLL_INTERVAL_MS = 2000

/** Maximum time to wait for a model switch before giving up */
const SWITCH_TIMEOUT_MS = 60000

function modelTitle(name: string): string {
  return MODEL_DESCRIPTIONS[name] ?? name
}

export function ModelSelector(): React.ReactElement {
  const selectedModel = useSidebarStore((s) => s.selectedModel)
  const setSelectedModel = useSidebarStore((s) => s.setSelectedModel)
  const isModelSwitching = useSidebarStore((s) => s.isModelSwitching)
  const setIsModelSwitching = useSidebarStore((s) => s.setIsModelSwitching)
  const llmReachable = useSidebarStore((s) => s.llmReachable)
  const [models, setModels] = useState<string[]>([DEFAULT_MODEL])
  const [currentModel, setCurrentModel] = useState<string>(DEFAULT_MODEL)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [switchError, setSwitchError] = useState<string | null>(null)
  const prevLlmRef = useRef(llmReachable)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const fetchModels = useCallback(() => {
    setFetchError(null)
    apiClient.models().then((data) => {
      if (data.models.length > 0) {
        setModels(data.models)
        setCurrentModel(data.current)
        setFetchError(null)
      }
    }).catch((err: unknown) => {
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown>
        if (body?.['error_code'] === 'LLM_DOWN') {
          setFetchError('LLM server is not running')
        } else {
          const parsed = parseErrorDetail(body)
          setFetchError(parsed !== 'An unexpected error occurred' ? parsed : 'Could not fetch models')
        }
      } else if (err instanceof TypeError && err.message === 'Failed to fetch') {
        setFetchError('Cannot reach backend')
      } else {
        setFetchError('Could not fetch models')
      }
    })
  }, [])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  // Re-fetch when LLM server transitions from unreachable → reachable
  useEffect(() => {
    if (llmReachable && !prevLlmRef.current) {
      fetchModels()
    }
    prevLlmRef.current = llmReachable
  }, [llmReachable, fetchModels])

  // Re-fetch models when the document becomes visible (e.g. after backend reconnect)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') fetchModels()
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [fetchModels])

  // Clean up poll timer on unmount
  useEffect(() => clearPollTimer, [clearPollTimer])

  const handleModelChange = useCallback((newModel: string) => {
    // If same as current loaded model, just update local selection
    if (newModel === currentModel) {
      setSelectedModel(newModel)
      setSwitchError(null)
      return
    }

    const previousModel = selectedModel
    setSelectedModel(newModel)
    setSwitchError(null)
    setIsModelSwitching(true)

    apiClient.switchModel(newModel).then(() => {
      // Switch initiated — poll until LLM is ready with the new model
      const startTime = Date.now()

      const poll = () => {
        if (Date.now() - startTime > SWITCH_TIMEOUT_MS) {
          setIsModelSwitching(false)
          setSwitchError('Switch timed out — LLM may still be loading')
          setSelectedModel(previousModel)
          return
        }

        apiClient.models().then((data) => {
          if (data.current === newModel) {
            // Switch complete
            setModels(data.models)
            setCurrentModel(data.current)
            setIsModelSwitching(false)
            setSwitchError(null)
          } else {
            // Still switching — poll again
            pollTimerRef.current = setTimeout(poll, SWITCH_POLL_INTERVAL_MS)
          }
        }).catch(() => {
          // Backend temporarily unreachable during restart — keep polling
          pollTimerRef.current = setTimeout(poll, SWITCH_POLL_INTERVAL_MS)
        })
      }

      pollTimerRef.current = setTimeout(poll, SWITCH_POLL_INTERVAL_MS)
    }).catch((err: unknown) => {
      setIsModelSwitching(false)
      setSelectedModel(previousModel)
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown>
        const parsed = parseErrorDetail(body)
        setSwitchError(parsed !== 'An unexpected error occurred' ? parsed : 'Failed to switch model')
      } else {
        debugError('Model switch error:', err)
        setSwitchError('Failed to switch model')
      }
    })
  }, [currentModel, selectedModel, setSelectedModel, setIsModelSwitching])

  return (
    <div className="control-row">
      <label htmlFor="model-select">Model</label>
      <div className="model-select-wrapper">
        <select
          id="model-select"
          value={selectedModel}
          onChange={(e) => handleModelChange(e.target.value)}
          disabled={isModelSwitching}
          aria-label="Select LLM model"
          aria-busy={isModelSwitching}
        >
          {models.map((m) => (
            <option key={m} value={m} title={modelTitle(m)}>{m}</option>
          ))}
        </select>
        {isModelSwitching && (
          <span className="support-text switch-status" aria-live="polite">
            Switching model\u2026
          </span>
        )}
      </div>
      {fetchError && !isModelSwitching && (
        <span className="support-text error-text">({fetchError})</span>
      )}
      {switchError && !isModelSwitching && (
        <span className="support-text error-text" role="alert">({switchError})</span>
      )}
    </div>
  )
}
