import { useState, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { managementApi, ApiError } from '../api'
import { showToast } from '@/shared/components/Toast'

interface ImportSectionProps {
  isOpen: boolean
  onToggle: () => void
  sectionRef: (node: HTMLDivElement | null) => void
}

const ACCEPTED_TYPES = '.pdf,.html,.htm,.json,.csv'
const MAX_SIZE_MB = 10
const ALLOWED_PROTOCOLS = ['http:', 'https:']

/** Returns an error message if the URL is invalid, or null if it's acceptable. */
function validateImportUrl(raw: string): string | null {
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    return 'Please enter a valid URL (e.g. https://example.com/article)'
  }
  if (!ALLOWED_PROTOCOLS.includes(parsed.protocol)) {
    return 'Only http:// and https:// URLs are allowed'
  }
  return null
}

export function ImportSection({ isOpen, onToggle, sectionRef }: ImportSectionProps): React.ReactElement {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadingFile, setUploadingFile] = useState('')
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number }>({ current: 0, total: 0 })
  const [urlValue, setUrlValue] = useState('')
  const [urlError, setUrlError] = useState<string | null>(null)
  const [importingUrl, setImportingUrl] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const invalidateAll = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['articles'] })
    void queryClient.invalidateQueries({ queryKey: ['stats'] })
  }, [queryClient])

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const fileArr = Array.from(files)
    if (fileArr.length === 0) return

    for (let i = 0; i < fileArr.length; i++) {
      const file = fileArr[i]
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        showToast(`${file.name} exceeds ${MAX_SIZE_MB}MB limit`, 'error')
        continue
      }

      setUploading(true)
      setUploadingFile(file.name)
      setUploadProgress({ current: i + 1, total: fileArr.length })
      try {
        const result = await managementApi.uploadFile(file)
        // If the response includes a warning, keep the toast visible until dismissed
        if (result.warning) {
          showToast(`Imported "${result.filename}" (${result.chunks_ingested} chunks) — ${result.warning}`, 'success', { persistent: true })
        } else {
          showToast(`Imported "${result.filename}" (${result.chunks_ingested} chunks)`, 'success')
        }
        invalidateAll()
      } catch (err) {
        const detail = err instanceof ApiError ? ((err.body as { detail?: string })?.detail ?? `Failed to import "${file.name}"`) : `Failed to import "${file.name}"`
        showToast(detail, 'error')
      } finally {
        setUploading(false)
        setUploadingFile('')
      }
    }
  }, [invalidateAll])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (uploading) return
    void handleFiles(e.dataTransfer.files)
  }, [uploading, handleFiles])

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    setUrlValue(e.target.value)
    // Clear error as user types
    if (urlError) setUrlError(null)
  }

  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = urlValue.trim()
    if (!trimmed) return

    const validationError = validateImportUrl(trimmed)
    if (validationError) {
      setUrlError(validationError)
      return
    }

    setImportingUrl(true)
    try {
      const result = await managementApi.ingestUrl(trimmed)
      // Keep warning toasts visible until user dismisses them
      if (result.warning) {
        showToast(`Imported URL (${result.chunks_ingested} chunks) — ${result.warning}`, 'success', { persistent: true })
      } else {
        showToast(`Imported URL (${result.chunks_ingested} chunks)`, 'success')
      }
      setUrlValue('')
      setUrlError(null)
      invalidateAll()
    } catch (err) {
      showToast(err instanceof ApiError ? ((err.body as { detail?: string })?.detail ?? 'Failed to import URL') : 'Failed to import URL', 'error')
    } finally {
      setImportingUrl(false)
    }
  }

  const isDisabled = uploading || importingUrl

  return (
    <div className="import-section" ref={sectionRef}>
      <button
        type="button"
        className="import-section-trigger"
        onClick={onToggle}
        aria-expanded={isOpen ? "true" : "false"}
      >
        <span className={`chevron${isOpen ? ' open' : ''}`} />
        <span className="import-section-label">Import</span>
      </button>

      {isOpen && (
        <div className="import-section-body">
          {/* File upload drop zone */}
          <div
            className={`import-drop-zone${dragOver ? ' drag-over' : ''}${isDisabled ? ' disabled' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => !isDisabled && fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Drop files here or click to browse"
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click() } }}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            {uploading ? (
              <div className="import-upload-progress">
                <p className="import-upload-filename">{uploadingFile}</p>
                {uploadProgress.total > 1 && (
                  <p className="import-drop-hint">File {uploadProgress.current} of {uploadProgress.total}</p>
                )}
                <div className="import-progress-track">
                  <div className="import-progress-fill" style={{ width: uploadProgress.total > 1 ? `${Math.round((uploadProgress.current / uploadProgress.total) * 100)}%` : '100%' }} />
                </div>
              </div>
            ) : (
              <>
                <p>Drop files here or click to browse</p>
                <p className="import-drop-hint">PDF, HTML, JSON, CSV &mdash; max {MAX_SIZE_MB}MB each</p>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_TYPES}
              multiple
              hidden
              onChange={e => { if (e.target.files) void handleFiles(e.target.files); e.target.value = '' }}
            />
          </div>

          {/* URL import */}
          <div className="import-url-divider">
            <span>or import from URL</span>
          </div>
          <form className="import-url-form" onSubmit={handleUrlSubmit}>
            <div className="import-url-row">
              <input
                type="text"
                className={`import-url-input${urlError ? ' input-error' : ''}`}
                placeholder="https://example.com/article"
                value={urlValue}
                onChange={handleUrlChange}
                disabled={isDisabled}
                aria-describedby={urlError ? 'url-error' : undefined}
                aria-invalid={urlError ? "true" : "false"}
              />
              <button
                type="submit"
                className="primary-btn"
                disabled={isDisabled || !urlValue.trim()}
              >
                {importingUrl ? 'Importing...' : 'Import URL'}
              </button>
            </div>
            {urlError && (
              <p id="url-error" className="import-url-error" role="alert">{urlError}</p>
            )}
          </form>
        </div>
      )}
    </div>
  )
}
