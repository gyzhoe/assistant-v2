import { useState, useRef, useCallback, useEffect } from 'react'
import { apiClient } from '../../lib/api-client'
import { ApiError } from '../../lib/api-client'
import type { IngestUploadResponse } from '../../shared/types'
import { debugLog } from '../../shared/constants'

const ALLOWED_EXTENSIONS = ['.json', '.csv', '.html', '.htm', '.pdf']
const MAX_FILES = 10
const SUCCESS_DISMISS_MS = 4000

export interface StagedFile {
  id: string
  file: File
  name: string
  extension: string
  sizeLabel: string
}

export type UploadStatus = 'idle' | 'uploading' | 'success' | 'error'

export interface UploadProgress {
  current: number
  total: number
  currentFile: string
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getExtension(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx).toLowerCase() : ''
}

export function useKnowledgeImport() {
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([])
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle')
  const [progress, setProgress] = useState<UploadProgress | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [results, setResults] = useState<IngestUploadResponse[]>([])

  const abortRef = useRef<AbortController | null>(null)
  const dismissRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearDismissTimer = useCallback(() => {
    if (dismissRef.current) {
      clearTimeout(dismissRef.current)
      dismissRef.current = null
    }
  }, [])

  const resetState = useCallback(() => {
    clearDismissTimer()
    setStagedFiles([])
    setUploadStatus('idle')
    setProgress(null)
    setErrorMessage(null)
    setResults([])
  }, [clearDismissTimer])

  const addFiles = useCallback((files: File[]) => {
    setErrorMessage(null)

    const invalid = files.filter((f) => !ALLOWED_EXTENSIONS.includes(getExtension(f.name)))
    if (invalid.length > 0) {
      const names = invalid.map((f) => f.name).join(', ')
      setErrorMessage(`Unsupported file type: ${names}. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`)
      return
    }

    setStagedFiles((prev) => {
      const remaining = MAX_FILES - prev.length
      if (remaining <= 0) {
        setErrorMessage(`Maximum ${MAX_FILES} files allowed`)
        return prev
      }
      const toAdd = files.slice(0, remaining)
      if (toAdd.length < files.length) {
        setErrorMessage(`Only ${remaining} more file(s) can be added (max ${MAX_FILES})`)
      }
      return [
        ...prev,
        ...toAdd.map((file) => ({
          id: crypto.randomUUID(),
          file,
          name: file.name,
          extension: getExtension(file.name),
          sizeLabel: formatFileSize(file.size),
        })),
      ]
    })
  }, [])

  const removeFile = useCallback((id: string) => {
    setStagedFiles((prev) => prev.filter((f) => f.id !== id))
    setErrorMessage(null)
  }, [])

  const clearFiles = useCallback(() => {
    setStagedFiles([])
    setErrorMessage(null)
  }, [])

  const startUpload = useCallback(async () => {
    if (stagedFiles.length === 0) return

    const ctrl = new AbortController()
    abortRef.current = ctrl
    setUploadStatus('uploading')
    setErrorMessage(null)
    setResults([])

    const accumulated: IngestUploadResponse[] = []

    for (let i = 0; i < stagedFiles.length; i++) {
      if (ctrl.signal.aborted) break

      const file = stagedFiles[i]
      setProgress({ current: i + 1, total: stagedFiles.length, currentFile: file.name })

      try {
        const result = await apiClient.uploadFile(file.file, ctrl.signal)
        accumulated.push(result)
        debugLog(`Uploaded ${file.name}: ${result.chunks_ingested} chunks`)
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setUploadStatus('idle')
          setProgress(null)
          abortRef.current = null
          return
        }

        let message = 'Upload failed'
        if (err instanceof ApiError) {
          if (err.status === 503) message = 'Backend or Ollama is not reachable'
          else if (err.status === 409) message = 'Another import is already in progress'
          else {
            const body = err.body as { detail?: string }
            message = body?.detail ?? `Upload failed (${err.status})`
          }
        } else if (err instanceof Error) {
          message = err.message
        }

        setUploadStatus('error')
        setErrorMessage(message)
        setProgress(null)
        setResults(accumulated)
        abortRef.current = null
        return
      }
    }

    setResults(accumulated)
    setUploadStatus('success')
    setProgress(null)
    abortRef.current = null

    clearDismissTimer()
    dismissRef.current = setTimeout(() => {
      resetState()
    }, SUCCESS_DISMISS_MS)
  }, [stagedFiles, clearDismissTimer, resetState])

  const cancelUpload = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setUploadStatus('idle')
    setProgress(null)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
      if (dismissRef.current) {
        clearTimeout(dismissRef.current)
        dismissRef.current = null
      }
    }
  }, [])

  return {
    stagedFiles,
    uploadStatus,
    progress,
    errorMessage,
    results,
    addFiles,
    removeFile,
    clearFiles,
    startUpload,
    cancelUpload,
    resetState,
  }
}
