import React, { useEffect, useState } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient } from '../../lib/api-client'
import { DEFAULT_MODEL } from '../../shared/constants'

export function ModelSelector(): React.ReactElement {
  const selectedModel = useSidebarStore((s) => s.selectedModel)
  const setSelectedModel = useSidebarStore((s) => s.setSelectedModel)
  const [models, setModels] = useState<string[]>([DEFAULT_MODEL])

  useEffect(() => {
    apiClient.models().then((list) => {
      if (list.length > 0) setModels(list)
    }).catch(() => {
      // Keep default if models endpoint unavailable
    })
  }, [])

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
    </div>
  )
}
