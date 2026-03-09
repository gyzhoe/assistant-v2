import React from 'react'

export interface ConnectionSectionProps {
  backendUrl: string
  apiToken: string
  autoDetectMsg: string
  isDetecting: boolean
  onBackendUrlChange: (value: string) => void
  onApiTokenChange: (value: string) => void
  onAutoDetect: () => void
}

export function ConnectionSection({
  backendUrl,
  apiToken,
  autoDetectMsg,
  isDetecting,
  onBackendUrlChange,
  onApiTokenChange,
  onAutoDetect,
}: ConnectionSectionProps): React.ReactElement {
  return (
    <div className="options-section">
      <div className="options-section-header">
        <span className="options-section-label">Connection</span>
      </div>

      {/* Backend URL */}
      <div className="options-field">
        <label htmlFor="backendUrl" className="options-label">
          Backend URL
        </label>
        <input
          id="backendUrl"
          type="url"
          value={backendUrl}
          onChange={(e) => onBackendUrlChange(e.target.value)}
          className="options-input"
          placeholder="http://localhost:8765"
        />
        <p className="options-hint">URL of the local FastAPI backend server.</p>
      </div>

      {/* API Token */}
      <div className="options-field">
        <label htmlFor="apiToken" className="options-label">
          API Token
        </label>
        <div className="options-input-row">
          <input
            id="apiToken"
            type="password"
            value={apiToken}
            onChange={(e) => onApiTokenChange(e.target.value)}
            className="options-input font-mono"
            placeholder="Paste the API_TOKEN from the backend .env file"
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={onAutoDetect}
            disabled={isDetecting}
            className="options-btn-secondary"
            aria-label="Auto-detect API token from backend"
          >
            {isDetecting ? 'Detecting\u2026' : 'Auto-detect'}
          </button>
        </div>
        {autoDetectMsg && (
          <p className="options-hint font-medium" role="status" aria-live="polite">{autoDetectMsg}</p>
        )}
        <p className="options-hint">
          Shared secret configured in the backend <code>API_TOKEN</code> environment variable.
          Stored only on this device — never synced to other browsers.
          Leave blank if token auth is disabled on the backend.
        </p>
      </div>
    </div>
  )
}
