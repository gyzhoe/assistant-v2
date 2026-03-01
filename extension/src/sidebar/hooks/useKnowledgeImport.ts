import { useState, useRef, useCallback, useEffect } from 'react'
import { apiClient } from '../../lib/api-client'
import { ApiError } from '../../lib/api-client'
import type { IngestUploadResponse } from '../../shared/types'
import { debugLog } from '../../shared/constants'

const ALLOWED_EXTENSIONS = ['.json', '.csv', '.html', '.htm', '.pdf']
const MAX_FILES = 10
const SUCCESS_DISMISS_MS = 4000

export type FileUploadStatus = 'pending' | 'uploading' | 'success' | 'error'

export interface StagedFile {
  id: string
  file: File
  name: string
  extension: string
  sizeLabel: string
  uploadStatus: FileUploadStatus
  errorMessage: string | null
  result: IngestUploadResponse | null
}

export type UploadStatus = 'idle' | 'uploading' | 'success' | 'error' | 'partial'

export interface UploadProgress {
  current: number
  total: number
  currentFile: string
  succeeded: number
  failed: number
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

function parseUploadError(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { detail?: string; error_code?: string }
    if (body?.error_code === 'PAYLOAD_TOO_LARGE' || err.status === 413) {
      return 'File is too large. Please reduce the file size and try again.'
    }
    if (err.status === 503) return 'Backend or Ollama is not reachable'
    if (err.status === 409) return 'Another import is already in progress'
    return body?.detail ?? `Upload failed (${err.status})`
  }
  if (err instanceof Error) return err.message
  return 'Upload failed'
}

export function useKnowledgeImport() {
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([])
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle')
  const [progress, setProgress] = useState<UploadProgress | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

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
          uploadStatus: 'pending' as FileUploadStatus,
          errorMessage: null,
          result: null,
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

  const uploadFiles = useCallback(async (filesToUpload: StagedFile[]) => {
    if (filesToUpload.length === 0) return

    const ctrl = new AbortController()
    abortRef.current = ctrl
    setUploadStatus('uploading')
    setErrorMessage(null)

    let succeeded = 0
    let failed = 0

    for (let i = 0; i < filesToUpload.length; i++) {
      if (ctrl.signal.aborted) break

      const file = filesToUpload[i]
      setProgress({
        current: i + 1,
        total: filesToUpload.length,
        currentFile: file.name,
        succeeded,
        failed,
      })

      // Mark this file as uploading
      setStagedFiles((prev) =>
        prev.map((f) => f.id === file.id ? { ...f, uploadStatus: 'uploading' as FileUploadStatus, errorMessage: null } : f)
      )

      try {
        const result = await apiClient.uploadFile(file.file, ctrl.signal)
        succeeded++
        debugLog(`Uploaded ${file.name}: ${result.chunks_ingested} chunks`)
        setStagedFiles((prev) =>
          prev.map((f) => f.id === file.id ? { ...f, uploadStatus: 'success' as FileUploadStatus, result } : f)
        )
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          // Reset uploading files back to pending on cancel
          setStagedFiles((prev) =>
            prev.map((f) => f.uploadStatus === 'uploading' ? { ...f, uploadStatus: 'pending' as FileUploadStatus } : f)
          )
          setUploadStatus('idle')
          setProgress(null)
          abortRef.current = null
          return
        }

        failed++
        const message = parseUploadError(err)
        setStagedFiles((prev) =>
          prev.map((f) => f.id === file.id ? { ...f, uploadStatus: 'error' as FileUploadStatus, errorMessage: message } : f)
        )
      }
    }

    setProgress(null)
    abortRef.current = null

    if (failed > 0 && succeeded > 0) {
      setUploadStatus('partial')
    } else if (failed > 0) {
      setUploadStatus('error')
      setErrorMessage(`All ${failed} file${failed !== 1 ? 's' : ''} failed to upload`)
    } else {
      setUploadStatus('success')
      clearDismissTimer()
      dismissRef.current = setTimeout(() => {
        resetState()
      }, SUCCESS_DISMISS_MS)
    }
  }, [clearDismissTimer, resetState])

  const startUpload = useCallback(async () => {
    const pending = stagedFiles.filter((f) => f.uploadStatus === 'pending')
    if (pending.length === 0) return
    await uploadFiles(pending)
  }, [stagedFiles, uploadFiles])

  const retryFailed = useCallback(async () => {
    // Reset failed files to pending first
    setStagedFiles((prev) =>
      prev.map((f) => f.uploadStatus === 'error' ? { ...f, uploadStatus: 'pending' as FileUploadStatus, errorMessage: null } : f)
    )
    // We need to use a microtask to ensure state is updated before reading it
    // Instead, collect failed file IDs now and filter from updated state inside uploadFiles
    const failedFiles = stagedFiles.filter((f) => f.uploadStatus === 'error')
    if (failedFiles.length === 0) return
    await uploadFiles(failedFiles)
  }, [stagedFiles, uploadFiles])

  const cancelUpload = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setUploadStatus('idle')
    setProgress(null)
  }, [])

  /** Computed summary of per-file statuses */
  const fileSummary = {
    total: stagedFiles.length,
    succeeded: stagedFiles.filter((f) => f.uploadStatus === 'success').length,
    failed: stagedFiles.filter((f) => f.uploadStatus === 'error').length,
    pending: stagedFiles.filter((f) => f.uploadStatus === 'pending').length,
    uploading: stagedFiles.filter((f) => f.uploadStatus === 'uploading').length,
  }

  const results = stagedFiles.filter((f) => f.result !== null).map((f) => f.result!)

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
    fileSummary,
    addFiles,
    removeFile,
    clearFiles,
    startUpload,
    retryFailed,
    cancelUpload,
    resetState,
  }
}
