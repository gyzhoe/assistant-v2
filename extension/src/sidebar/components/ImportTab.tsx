import React, { useRef, useState, useCallback } from 'react'
import { apiClient, ApiError } from '../../lib/api-client'
import { useKnowledgeImport } from '../hooks/useKnowledgeImport'

const ACCEPTED = '.json,.csv,.html,.htm,.pdf'

export function ImportTab(): React.ReactElement {
  const {
    stagedFiles, uploadStatus, progress, errorMessage, results,
    addFiles, removeFile, clearFiles, startUpload, cancelUpload, resetState,
  } = useKnowledgeImport()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragCount, setDragCount] = useState(0)
  const [urlInput, setUrlInput] = useState('')
  const [urlLoading, setUrlLoading] = useState(false)
  const [urlError, setUrlError] = useState<string | null>(null)
  const [urlSuccess, setUrlSuccess] = useState<string | null>(null)

  const isDragOver = dragCount > 0
  const isUploading = uploadStatus === 'uploading'

  const handleUrlImport = useCallback(async () => {
    const url = urlInput.trim()
    if (!url) return
    setUrlLoading(true)
    setUrlError(null)
    setUrlSuccess(null)
    try {
      const result = await apiClient.ingestUrl(url)
      if (result.warning) {
        setUrlError(result.warning)
      } else {
        const label = result.title ?? url
        setUrlSuccess(`Imported "${label}" — ${result.chunks_ingested} chunks added`)
        setUrlInput('')
      }
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = (err.body as Record<string, string>)?.detail ?? 'Unknown error'
        setUrlError(detail)
      } else {
        setUrlError('Failed to import URL')
      }
    } finally {
      setUrlLoading(false)
    }
  }, [urlInput])

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragCount((c) => c + 1)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragCount((c) => c - 1)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragCount(0)
    addFiles([...e.dataTransfer.files])
  }, [addFiles])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      addFiles([...e.target.files])
      e.target.value = ''
    }
  }, [addFiles])

  const handleDropZoneClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleDropZoneKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      fileInputRef.current?.click()
    }
  }, [])

  // Success summary
  if (uploadStatus === 'success') {
    const totalChunks = results.reduce((sum, r) => sum + r.chunks_ingested, 0)
    const warnings = results.filter((r) => r.warning).map((r) => r.warning)
    return (
      <div className="kb-progress">
        <p className="support-text" style={{ color: 'var(--ok-text)' }}>
          {results.length} file{results.length !== 1 ? 's' : ''} imported, {totalChunks} chunks added
        </p>
        {warnings.map((w, i) => (
          <p key={i} className="support-text" style={{ color: 'var(--warn-text)' }}>
            {w}
          </p>
        ))}
      </div>
    )
  }

  // Error state
  if (uploadStatus === 'error') {
    return (
      <div className="kb-progress">
        <div className="alert-banner error">
          <p className="alert-title">Import failed</p>
          <p className="alert-message">{errorMessage}</p>
        </div>
        <div className="control-row">
          <button className="secondary-btn" onClick={resetState}>Clear</button>
          <button className="primary-btn" onClick={startUpload}>Retry</button>
        </div>
      </div>
    )
  }

  // Uploading state
  if (isUploading && progress) {
    const pct = Math.round((progress.current / progress.total) * 100)
    return (
      <div className="kb-progress">
        <p className="kb-progress-text">
          Processing file {progress.current}/{progress.total}: {progress.currentFile}
        </p>
        <div className="kb-progress-track">
          <div className="kb-progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <button className="secondary-btn error cancel-btn" onClick={cancelUpload}>
          Cancel
        </button>
      </div>
    )
  }

  return (
    <>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        aria-hidden="true"
      />

      {/* Drop zone */}
      <div
        className={`kb-drop-zone${isDragOver ? ' drag-over' : ''}${isUploading ? ' disabled' : ''}`}
        role="button"
        tabIndex={0}
        aria-label="Drop files here or click to browse"
        onClick={handleDropZoneClick}
        onKeyDown={handleDropZoneKeyDown}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        Drop files here or click to browse
        <br />
        <span className="kb-file-size">PDF, HTML, JSON, CSV</span>
      </div>

      {/* URL import section */}
      <div className="kb-url-section">
        <div className="kb-url-divider">
          <span>or import from URL</span>
        </div>
        <div className="kb-url-row">
          <input
            type="url"
            className="kb-url-input"
            placeholder="https://example.com/article"
            value={urlInput}
            onChange={(e) => { setUrlInput(e.target.value); setUrlError(null); setUrlSuccess(null) }}
            disabled={urlLoading || isUploading}
          />
          <button
            className="primary-btn"
            onClick={handleUrlImport}
            disabled={!urlInput.trim() || urlLoading || isUploading}
          >
            {urlLoading ? 'Importing...' : 'Import'}
          </button>
        </div>
        {urlError && <p className="support-text error-text" role="alert">{urlError}</p>}
        {urlSuccess && <p className="support-text" style={{ color: 'var(--ok-text)' }}>{urlSuccess}</p>}
      </div>

      {/* Error message */}
      {errorMessage && (
        <p className="support-text error-text" role="alert">{errorMessage}</p>
      )}

      {/* Staged file list */}
      {stagedFiles.length > 0 && (
        <>
          <div className="kb-file-list">
            {stagedFiles.map((f) => (
              <div key={f.id} className="kb-file-row">
                <span className="kb-file-type-badge">{f.extension.replace('.', '')}</span>
                <span className="kb-file-name" title={f.name}>{f.name}</span>
                <span className="kb-file-size">{f.sizeLabel}</span>
                <button
                  className="kb-file-remove"
                  onClick={() => removeFile(f.id)}
                  aria-label={`Remove ${f.name}`}
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
          <div className="control-row">
            <button className="secondary-btn" onClick={clearFiles}>Clear</button>
            <button
              className="primary-btn"
              onClick={startUpload}
              disabled={isUploading}
            >
              Import {stagedFiles.length} file{stagedFiles.length !== 1 ? 's' : ''}
            </button>
          </div>
        </>
      )}
    </>
  )
}
