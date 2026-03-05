import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient, ApiError } from '../../lib/api-client'
import { parseErrorDetail } from '../../lib/error-utils'
import { DEFAULT_MODEL } from '../../shared/constants'

const MODEL_DESCRIPTIONS: Record<string, string> = {
  'qwen3.5:9b': '9B — fast, excellent quality',
  'llama3.2:3b': '3B parameters — fast, lighter quality',
}

function modelTitle(name: string): string {
  return MODEL_DESCRIPTIONS[name] ?? name
}

export function ModelSelector(): React.ReactElement {
  const selectedModel = useSidebarStore((s) => s.selectedModel)
  const setSelectedModel = useSidebarStore((s) => s.setSelectedModel)
  const ollamaReachable = useSidebarStore((s) => s.ollamaReachable)
  const [models, setModels] = useState<string[]>([DEFAULT_MODEL])
  const [fetchError, setFetchError] = useState<string | null>(null)
  const prevOllamaRef = useRef(ollamaReachable)

  const fetchModels = useCallback(() => {
    setFetchError(null)
    apiClient.models().then((list) => {
      if (list.length > 0) {
        setModels(list)
        setFetchError(null)
      }
    }).catch((err: unknown) => {
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown>
        if (body?.['error_code'] === 'OLLAMA_DOWN') {
          setFetchError('Ollama is not running')
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

  // Re-fetch when Ollama transitions from unreachable → reachable
  useEffect(() => {
    if (ollamaReachable && !prevOllamaRef.current) {
      fetchModels()
    }
    prevOllamaRef.current = ollamaReachable
  }, [ollamaReachable, fetchModels])

  // Re-fetch models when the document becomes visible (e.g. after backend reconnect)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') fetchModels()
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [fetchModels])

  return (
    <div className="control-row">
      <label htmlFor="model-select">Model</label>
      <select
        id="model-select"
        value={selectedModel}
        onChange={(e) => setSelectedModel(e.target.value)}
        aria-label="Select LLM model"
      >
        {models.map((m) => (
          <option key={m} value={m} title={modelTitle(m)}>{m}</option>
        ))}
      </select>
      {fetchError && (
        <span className="support-text error-text">({fetchError})</span>
      )}
    </div>
  )
}
