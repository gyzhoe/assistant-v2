import React, { useState, useCallback } from 'react'
import { apiClient } from '../../lib/api-client'

interface ManageTabProps {
  docCounts: Record<string, number>
  onRefresh: () => void
}

const COLLECTION_LABELS: Record<string, string> = {
  whd_tickets: 'Tickets',
  kb_articles: 'KB Articles',
}

function formatCollectionName(name: string): string {
  return COLLECTION_LABELS[name] ?? name
}

export function ManageTab({ docCounts, onRefresh }: ManageTabProps): React.ReactElement {
  const [confirmingClear, setConfirmingClear] = useState<string | null>(null)
  const [clearingCollection, setClearingCollection] = useState<string | null>(null)

  const collections = Object.entries(docCounts).filter(([, count]) => count > 0)

  const handleClear = useCallback(async (name: string) => {
    setClearingCollection(name)
    setConfirmingClear(null)
    try {
      await apiClient.clearCollection(name)
      onRefresh()
    } finally {
      setClearingCollection(null)
    }
  }, [onRefresh])

  if (collections.length === 0) {
    return <p className="support-text">No documents imported yet</p>
  }

  return (
    <div className="kb-collection-list">
      {collections.map(([name, count]) => (
        <div key={name} className="kb-collection-row">
          <span className="kb-file-name">{formatCollectionName(name)}</span>
          <span className="kb-file-size">{count} docs</span>

          {clearingCollection === name ? (
            <span className="svc-action">Clearing…</span>
          ) : confirmingClear === name ? (
            <>
              <span className="kb-file-size">Sure?</span>
              <button
                className="svc-btn danger"
                onClick={() => handleClear(name)}
              >
                Yes
              </button>
              <button
                className="svc-btn success"
                onClick={() => setConfirmingClear(null)}
              >
                No
              </button>
            </>
          ) : (
            <button
              className="svc-btn danger"
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
