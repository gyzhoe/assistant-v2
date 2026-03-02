import React, { useState, useEffect, useRef, useCallback } from 'react'
import { apiClient } from '../../lib/api-client'
import { ImportTab } from './ImportTab'
import { ManageTab } from './ManageTab'

const POLL_INTERVAL_MS = 10000

export function KnowledgePanel(): React.ReactElement {
  const [collapsed, setCollapsed] = useState(true)
  const [activeTab, setActiveTab] = useState<'import' | 'manage'>('import')
  const [docCounts, setDocCounts] = useState<Record<string, number>>({})
  const mountedRef = useRef(true)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const totalDocs = Object.values(docCounts).reduce((sum, n) => sum + n, 0)

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const fetchCounts = useCallback(async () => {
    try {
      const h = await apiClient.health()
      if (mountedRef.current) setDocCounts(h.chroma_doc_counts)
    } catch {
      // Ignore — backend may be offline
    }
  }, [])

  const schedulePoll = useCallback(() => {
    clearTimer()
    timerRef.current = setTimeout(() => {
      if (mountedRef.current) {
        fetchCounts().finally(() => {
          if (mountedRef.current) schedulePoll()
        })
      }
    }, POLL_INTERVAL_MS)
  }, [fetchCounts, clearTimer])

  useEffect(() => {
    mountedRef.current = true
    fetchCounts().finally(() => {
      if (mountedRef.current) schedulePoll()
    })
    return () => {
      mountedRef.current = false
      clearTimer()
    }
  }, [fetchCounts, schedulePoll, clearTimer])

  const handleRefresh = useCallback(() => {
    clearTimer()
    fetchCounts().finally(() => {
      if (mountedRef.current) schedulePoll()
    })
  }, [fetchCounts, schedulePoll, clearTimer])

  return (
    <section className="panel" aria-label="Knowledge Base">
      <button
        className="section-heading-row collapsible-trigger"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
        aria-controls="kb-panel-body"
      >
        <h2 className="section-heading">Knowledge Base</h2>
        <div className="heading-right">
          <span className={`status-chip ${totalDocs > 0 ? 'ok' : 'pending'}`}>
            {totalDocs} docs
          </span>
          <span className={`chevron ${collapsed ? '' : 'open'}`} aria-hidden="true" />
        </div>
      </button>

      {!collapsed && (
        <div id="kb-panel-body" className="collapsible-body">
          <div className="kb-tab-strip" role="tablist" aria-label="Knowledge base tabs" aria-orientation="horizontal">
            <button
              id="kb-tab-import"
              role="tab"
              className={`kb-tab ${activeTab === 'import' ? 'active' : ''}`}
              aria-selected={activeTab === 'import'}
              aria-controls="kb-tab-panel-import"
              onClick={() => setActiveTab('import')}
            >
              Import
            </button>
            <button
              id="kb-tab-manage"
              role="tab"
              className={`kb-tab ${activeTab === 'manage' ? 'active' : ''}`}
              aria-selected={activeTab === 'manage'}
              aria-controls="kb-tab-panel-manage"
              onClick={() => setActiveTab('manage')}
            >
              Manage
            </button>
          </div>

          {activeTab === 'import' ? (
            <div role="tabpanel" id="kb-tab-panel-import" aria-labelledby="kb-tab-import">
              <ImportTab />
            </div>
          ) : (
            <div role="tabpanel" id="kb-tab-panel-manage" aria-labelledby="kb-tab-manage">
              <ManageTab docCounts={docCounts} onRefresh={handleRefresh} onSwitchToImport={() => setActiveTab('import')} />
            </div>
          )}
        </div>
      )}
    </section>
  )
}
