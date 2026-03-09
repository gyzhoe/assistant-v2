import React from 'react'
import type { AppSettings } from '../../shared/types'

export interface ModelPromptSectionProps {
  defaultModel: string
  promptSuffix: string
  theme: AppSettings['theme']
  models: string[]
  onDefaultModelChange: (value: string) => void
  onPromptSuffixChange: (value: string) => void
  onThemeChange: (value: AppSettings['theme']) => void
}

export function ModelPromptSection({
  defaultModel,
  promptSuffix,
  theme,
  models,
  onDefaultModelChange,
  onPromptSuffixChange,
  onThemeChange,
}: ModelPromptSectionProps): React.ReactElement {
  return (
    <>
      {/* Model & Prompt */}
      <div className="options-section">
        <div className="options-section-header">
          <span className="options-section-label">Model &amp; Prompt</span>
        </div>

        {/* Default model */}
        <div className="options-field">
          <label htmlFor="defaultModel" className="options-label">
            Default Model
          </label>
          <select
            id="defaultModel"
            value={defaultModel}
            onChange={(e) => onDefaultModelChange(e.target.value)}
            className="options-input"
            aria-label="Select default LLM model"
          >
            {(models.length > 0 ? models : [defaultModel]).map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <p className="options-hint">
            LLM model used for reply generation. Fetch available models by visiting the backend health endpoint.
          </p>
        </div>

        {/* Prompt suffix */}
        <div className="options-field">
          <label htmlFor="promptSuffix" className="options-label">
            Prompt Suffix
          </label>
          <textarea
            id="promptSuffix"
            value={promptSuffix}
            onChange={(e) => onPromptSuffixChange(e.target.value)}
            rows={3}
            className="options-input resize-none font-mono"
            placeholder="e.g. Always sign replies with 'IT Support Team'"
          />
          <p className="options-hint">
            Custom instructions appended to every prompt.
          </p>
        </div>
      </div>

      {/* Appearance */}
      <div className="options-section">
        <div className="options-section-header">
          <span className="options-section-label">Appearance</span>
        </div>

        <div className="options-field">
          <label htmlFor="theme" className="options-label">
            Theme
          </label>
          <select
            id="theme"
            value={theme}
            onChange={(e) => onThemeChange(e.target.value as AppSettings['theme'])}
            className="options-input"
            aria-label="Select theme"
          >
            <option value="system">System default</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>
      </div>
    </>
  )
}
