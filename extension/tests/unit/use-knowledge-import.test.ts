import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
  runtime: {
    sendMessage: vi.fn().mockResolvedValue(undefined),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
  },
})

// Mock apiClient
const mockUploadFile = vi.fn()
vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    uploadFile: (...args: unknown[]) => mockUploadFile(...args),
  },
  ApiError: class ApiError extends Error {
    constructor(public readonly status: number, public readonly body: unknown) {
      super(`API error ${status}`)
    }
  },
}))

// Mock crypto.randomUUID
let uuidCounter = 0
vi.stubGlobal('crypto', {
  randomUUID: () => `uuid-${++uuidCounter}`,
})

describe('useKnowledgeImport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    uuidCounter = 0
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('has correct initial state', async () => {
    const { useKnowledgeImport } = await import('../../src/sidebar/hooks/useKnowledgeImport')
    const { result } = renderHook(() => useKnowledgeImport())

    expect(result.current.stagedFiles).toEqual([])
    expect(result.current.uploadStatus).toBe('idle')
    expect(result.current.progress).toBeNull()
    expect(result.current.errorMessage).toBeNull()
    expect(result.current.results).toEqual([])
  })

  it('addFiles with valid extensions adds to stagedFiles', async () => {
    const { useKnowledgeImport } = await import('../../src/sidebar/hooks/useKnowledgeImport')
    const { result } = renderHook(() => useKnowledgeImport())

    const pdf = new File(['pdf content'], 'report.pdf', { type: 'application/pdf' })
    const html = new File(['<html></html>'], 'doc.html', { type: 'text/html' })

    act(() => {
      result.current.addFiles([pdf, html])
    })

    expect(result.current.stagedFiles).toHaveLength(2)
    expect(result.current.stagedFiles[0].name).toBe('report.pdf')
    expect(result.current.stagedFiles[0].extension).toBe('.pdf')
    expect(result.current.stagedFiles[1].name).toBe('doc.html')
    expect(result.current.errorMessage).toBeNull()
  })

  it('addFiles with invalid extension sets error and does not add file', async () => {
    const { useKnowledgeImport } = await import('../../src/sidebar/hooks/useKnowledgeImport')
    const { result } = renderHook(() => useKnowledgeImport())

    const docx = new File(['content'], 'report.docx', { type: 'application/vnd.openxmlformats' })

    act(() => {
      result.current.addFiles([docx])
    })

    expect(result.current.stagedFiles).toHaveLength(0)
    expect(result.current.errorMessage).toContain('Unsupported file type')
    expect(result.current.errorMessage).toContain('report.docx')
  })

  it('addFiles enforces 10-file max', async () => {
    const { useKnowledgeImport } = await import('../../src/sidebar/hooks/useKnowledgeImport')
    const { result } = renderHook(() => useKnowledgeImport())

    // Add 10 files
    const files = Array.from({ length: 10 }, (_, i) =>
      new File(['x'], `file${i}.pdf`, { type: 'application/pdf' })
    )
    act(() => {
      result.current.addFiles(files)
    })
    expect(result.current.stagedFiles).toHaveLength(10)

    // Try to add one more
    act(() => {
      result.current.addFiles([new File(['x'], 'extra.pdf', { type: 'application/pdf' })])
    })
    expect(result.current.stagedFiles).toHaveLength(10)
    expect(result.current.errorMessage).toContain('Maximum 10 files')
  })

  it('removeFile removes by id', async () => {
    const { useKnowledgeImport } = await import('../../src/sidebar/hooks/useKnowledgeImport')
    const { result } = renderHook(() => useKnowledgeImport())

    act(() => {
      result.current.addFiles([
        new File(['a'], 'a.pdf', { type: 'application/pdf' }),
        new File(['b'], 'b.pdf', { type: 'application/pdf' }),
      ])
    })

    const idToRemove = result.current.stagedFiles[0].id
    act(() => {
      result.current.removeFile(idToRemove)
    })

    expect(result.current.stagedFiles).toHaveLength(1)
    expect(result.current.stagedFiles[0].name).toBe('b.pdf')
  })

  it('startUpload calls uploadFile per file sequentially and updates progress', async () => {
    mockUploadFile.mockResolvedValue({
      filename: 'test.pdf',
      collection: 'kb_articles',
      chunks_ingested: 5,
      processing_time_ms: 100,
      warning: null,
    })

    const { useKnowledgeImport } = await import('../../src/sidebar/hooks/useKnowledgeImport')
    const { result } = renderHook(() => useKnowledgeImport())

    act(() => {
      result.current.addFiles([
        new File(['a'], 'a.pdf', { type: 'application/pdf' }),
        new File(['b'], 'b.pdf', { type: 'application/pdf' }),
      ])
    })

    await act(async () => {
      await result.current.startUpload()
    })

    expect(mockUploadFile).toHaveBeenCalledTimes(2)
    expect(result.current.uploadStatus).toBe('success')
    expect(result.current.results).toHaveLength(2)
  })

  it('cancelUpload aborts in-flight upload and resets to idle', async () => {
    // Make uploadFile hang indefinitely until aborted
    mockUploadFile.mockImplementation((_file: File, signal?: AbortSignal) => {
      return new Promise((_resolve, reject) => {
        signal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'))
        })
      })
    })

    const { useKnowledgeImport } = await import('../../src/sidebar/hooks/useKnowledgeImport')
    const { result } = renderHook(() => useKnowledgeImport())

    act(() => {
      result.current.addFiles([new File(['a'], 'a.pdf', { type: 'application/pdf' })])
    })

    // Start upload (don't await — it will hang)
    let uploadPromise: Promise<void>
    act(() => {
      uploadPromise = result.current.startUpload()
    })

    // Cancel
    act(() => {
      result.current.cancelUpload()
    })

    await act(async () => {
      await uploadPromise!
    })

    expect(result.current.uploadStatus).toBe('idle')
  })

  it('auto-dismisses success after 4 seconds', async () => {
    mockUploadFile.mockResolvedValue({
      filename: 'test.pdf',
      collection: 'kb_articles',
      chunks_ingested: 5,
      processing_time_ms: 100,
      warning: null,
    })

    const { useKnowledgeImport } = await import('../../src/sidebar/hooks/useKnowledgeImport')
    const { result } = renderHook(() => useKnowledgeImport())

    act(() => {
      result.current.addFiles([new File(['a'], 'a.pdf', { type: 'application/pdf' })])
    })

    await act(async () => {
      await result.current.startUpload()
    })

    expect(result.current.uploadStatus).toBe('success')

    // Advance past the 4-second auto-dismiss
    act(() => {
      vi.advanceTimersByTime(4000)
    })

    expect(result.current.uploadStatus).toBe('idle')
    expect(result.current.stagedFiles).toEqual([])
  })
})
