import React from 'react'
import type { ModelDownloadStatus, ModelInfo } from '../../shared/types'

export interface LLMModelsSectionProps {
  modelInfo: Record<string, ModelInfo>
  backendReachable: boolean
  downloadStatus: ModelDownloadStatus | null
  downloadError: string
  onDownload: (ggufNames?: string[]) => void
  onCancelDownload: () => void
  onClearErrorAndRetry: () => void
}

/**
 * Resolve a GGUF filename back to its human-readable display name
 * by searching through the model info map.
 */
function ggufToDisplayName(gguf: string, modelInfo: Record<string, ModelInfo>): string {
  for (const [displayName, info] of Object.entries(modelInfo)) {
    if (info.gguf_name === gguf) return displayName
  }
  return gguf
}

export function LLMModelsSection({
  modelInfo,
  backendReachable,
  downloadStatus,
  downloadError,
  onDownload,
  onCancelDownload,
  onClearErrorAndRetry,
}: LLMModelsSectionProps): React.ReactElement | null {
  if (Object.keys(modelInfo).length === 0) return null

  return (
    <div className="options-section">
      <div className="options-section-header">
        <span className="options-section-label">LLM Models</span>
      </div>

      {!backendReachable && (
        <p className="options-hint options-hint--warn">
          Backend is not running. Start the backend from the sidebar, then refresh this page to download models.
        </p>
      )}

      <div className="model-list">
        {Object.entries(modelInfo).map(([name, info]) => (
          <div key={name} className="model-card">
            <span className="model-card-name">{name}</span>
            <span className="model-card-size">{info.description}</span>
            {info.downloaded ? (
              <span className="model-status-badge model-status-badge--downloaded">
                Downloaded
              </span>
            ) : (
              <button
                type="button"
                className="model-status-badge model-status-badge--download"
                onClick={() => onDownload([info.gguf_name])}
                disabled={downloadStatus?.downloading === true || !backendReachable}
              >
                Download
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Download progress */}
      {downloadStatus?.downloading && (
        <div className="model-progress">
          <p className="model-progress-label">
            {downloadStatus.current_model
              ? `Downloading ${ggufToDisplayName(downloadStatus.current_model, modelInfo)}\u2026`
              : 'Starting download\u2026'}
          </p>
          <div className="model-progress-bar-track">
            <div
              className="model-progress-bar-fill"
              style={{
                width: downloadStatus.bytes_total > 0
                  ? `${Math.round((downloadStatus.bytes_downloaded / downloadStatus.bytes_total) * 100)}%`
                  : '0%',
              }}
            />
          </div>
          <div className="model-progress-details">
            <span>
              {downloadStatus.bytes_total > 0
                ? `${(downloadStatus.bytes_downloaded / 1e9).toFixed(1)} / ${(downloadStatus.bytes_total / 1e9).toFixed(1)} GB`
                : 'Calculating\u2026'}
            </span>
            <span>
              {downloadStatus.models_completed} of {downloadStatus.models_total} model{downloadStatus.models_total !== 1 ? 's' : ''}
            </span>
          </div>
          <button
            type="button"
            className="options-btn-secondary"
            onClick={onCancelDownload}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Error */}
      {downloadError && (
        <div className="model-error">
          <p className="model-error-text">{downloadError}</p>
          <button
            type="button"
            className="options-btn-secondary"
            onClick={onClearErrorAndRetry}
          >
            Retry
          </button>
        </div>
      )}

      {/* Download All Missing button */}
      {!downloadStatus?.downloading && Object.values(modelInfo).some((m) => !m.downloaded) && (
        <button
          type="button"
          className="options-btn-secondary"
          onClick={() => onDownload()}
        >
          Download All Missing
        </button>
      )}
    </div>
  )
}
