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
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-neutral-100">
      <label htmlFor="model-select" className="text-xs text-neutral-500 flex-shrink-0">
        Model
      </label>
      <select
        id="model-select"
        value={selectedModel}
        onChange={(e) => setSelectedModel(e.target.value)}
        className="text-xs border border-neutral-300 rounded px-1.5 py-0.5 bg-white text-neutral-800 flex-1 min-w-0"
        aria-label="Select LLM model"
      >
        {models.map((m) => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>
    </div>
  )
}
