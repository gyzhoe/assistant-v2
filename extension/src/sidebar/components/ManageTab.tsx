import React, { useState, useCallback, useRef, useEffect } from 'react'
import { apiClient } from '../../lib/api-client'

interface ManageTabProps {
  docCounts: Record<string, number>
  onRefresh: () => void
  onSwitchToImport?: () => void
}

const COLLECTION_LABELS: Record<string, string> = {
  whd_tickets: 'Tickets',
  kb_articles: 'KB Articles',
}

const SUCCESS_DISMISS_MS = 3000

function formatCollectionName(name: string): string {
  return COLLECTION_LABELS[name] ?? name
}

export function ManageTab({ docCounts, onRefresh, onSwitchToImport }: ManageTabProps): React.ReactElement {
  const [confirmingClear, setConfirmingClear] = useState<string | null>(null)
  const [clearingCollection, setClearingCollection] = useState<string | null>(null)
  const [clearSuccess, setClearSuccess] = useState<string | null>(null)
  const [clearError, setClearError] = useState<string | null>(null)
  const noButtonRef = useRef<HTMLButtonElement>(null)

  const collections = Object.entries(docCounts).filter(([, count]) => count > 0)

  // Auto-focus "No" button when confirm appears
  useEffect(() => {
    if (confirmingClear) {
      noButtonRef.current?.focus()
    }
  }, [confirmingClear])

  // Auto-dismiss success message
  useEffect(() => {
    if (!clearSuccess) return
    const timer = setTimeout(() => setClearSuccess(null), SUCCESS_DISMISS_MS)
    return () => clearTimeout(timer)
  }, [clearSuccess])

  const handleClear = useCallback(async (name: string) => {
    setClearingCollection(name)
    setConfirmingClear(null)
    setClearError(null)
    setClearSuccess(null)
    try {
      await apiClient.clearCollection(name)
      setClearSuccess(`${formatCollectionName(name)} cleared successfully`)
      onRefresh()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to clear collection'
      setClearError(message)
    } finally {
      setClearingCollection(null)
    }
  }, [onRefresh])

  if (collections.length === 0) {
    return (
      <div className="kb-empty-state">
        <p className="support-text">No documents imported yet.</p>
        <p className="support-text">Import files or URLs to build your knowledge base.</p>
        {onSwitchToImport && (
          <button type="button" className="link-btn" onClick={onSwitchToImport}>
            Go to Import
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="kb-collection-list">
      {clearSuccess && (
        <p className="support-text ok-text" role="status">{clearSuccess}</p>
      )}
      {clearError && (
        <p className="support-text error-text" role="alert">{clearError}</p>
      )}
      {collections.map(([name, count]) => (
        <div key={name} className="kb-collection-row" aria-busy={clearingCollection === name ? 'true' : undefined}>
          <span className="kb-collection-name">{formatCollectionName(name)}</span>
          <span className="kb-file-size">{count} docs</span>

          {clearingCollection === name ? (
            <span className="svc-action">Clearing\u2026</span>
          ) : confirmingClear === name ? (
            <>
              <span className="kb-file-size">Sure?</span>
              <button
                className="manage-confirm-btn danger"
                onClick={() => handleClear(name)}
              >
                Yes
              </button>
              <button
                ref={noButtonRef}
                className="manage-confirm-btn success"
                onClick={() => setConfirmingClear(null)}
              >
                No
              </button>
            </>
          ) : (
            <button
              className="manage-confirm-btn danger"
              onClick={() => setConfirmingClear(name)}
            >
              Clear
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
