import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient } from '../../lib/api-client'
import { DEFAULT_MODEL } from '../../shared/constants'

export function ModelSelector(): React.ReactElement {
  const selectedModel = useSidebarStore((s) => s.selectedModel)
  const setSelectedModel = useSidebarStore((s) => s.setSelectedModel)
  const ollamaReachable = useSidebarStore((s) => s.ollamaReachable)
  const [models, setModels] = useState<string[]>([DEFAULT_MODEL])
  const [fetchError, setFetchError] = useState(false)
  const prevOllamaRef = useRef(ollamaReachable)

  const fetchModels = useCallback(() => {
    setFetchError(false)
    apiClient.models().then((list) => {
      if (list.length > 0) {
        setModels(list)
        setFetchError(false)
      }
    }).catch(() => {
      setFetchError(true)
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
          <option key={m} value={m}>{m}</option>
        ))}
      </select>
      {fetchError && (
        <span className="support-text error-text">(could not fetch models)</span>
      )}
    </div>
  )
}
