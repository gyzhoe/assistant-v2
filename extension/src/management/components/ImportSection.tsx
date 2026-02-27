import { useState, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { managementApi } from '../api'
import { showToast } from './Toast'

interface ImportSectionProps {
  isOpen: boolean
  onToggle: () => void
  sectionRef: (node: HTMLDivElement | null) => void
}

const ACCEPTED_TYPES = '.pdf,.html,.htm,.json,.csv'
const MAX_SIZE_MB = 10

export function ImportSection({ isOpen, onToggle, sectionRef }: ImportSectionProps): React.ReactElement {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [urlValue, setUrlValue] = useState('')
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

    for (const file of fileArr) {
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        showToast(`${file.name} exceeds ${MAX_SIZE_MB}MB limit`, 'error')
        continue
      }

      setUploading(true)
      try {
        const result = await managementApi.uploadFile(file)
        showToast(`Imported "${result.filename}" (${result.chunks_ingested} chunks)`, 'success')
        invalidateAll()
      } catch {
        showToast(`Failed to import "${file.name}"`, 'error')
      } finally {
        setUploading(false)
      }
    }
  }, [invalidateAll])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (uploading) return
    void handleFiles(e.dataTransfer.files)
  }, [uploading, handleFiles])

  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = urlValue.trim()
    if (!trimmed) return

    setImportingUrl(true)
    try {
      const result = await managementApi.ingestUrl(trimmed)
      showToast(`Imported URL (${result.chunks_ingested} chunks)`, 'success')
      setUrlValue('')
      invalidateAll()
    } catch {
      showToast('Failed to import URL', 'error')
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
        aria-expanded={isOpen}
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
              <p>Uploading...</p>
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
            <input
              type="url"
              className="import-url-input"
              placeholder="https://example.com/article"
              value={urlValue}
              onChange={e => setUrlValue(e.target.value)}
              disabled={isDisabled}
            />
            <button
              type="submit"
              className="primary-btn"
              disabled={isDisabled || !urlValue.trim()}
            >
              {importingUrl ? 'Importing...' : 'Import URL'}
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
