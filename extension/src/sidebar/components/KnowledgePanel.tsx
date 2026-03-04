import React, { useState, useCallback } from 'react'
import { apiClient } from '../../lib/api-client'
import { useSidebarStore } from '../store/sidebarStore'
import { ImportTab } from './ImportTab'
import { ManageTab } from './ManageTab'

export function KnowledgePanel(): React.ReactElement {
  const [collapsed, setCollapsed] = useState(true)
  const [activeTab, setActiveTab] = useState<'import' | 'manage'>('import')
  const docCounts = useSidebarStore((s) => s.chromaDocCounts)
  const setChromaDocCounts = useSidebarStore((s) => s.setChromaDocCounts)

  const totalDocs = Object.values(docCounts).reduce((sum, n) => sum + n, 0)

  const handleRefresh = useCallback(async () => {
    try {
      const h = await apiClient.health()
      setChromaDocCounts(h.chroma_doc_counts ?? {})
    } catch {
      // Ignore — backend may be offline
    }
  }, [setChromaDocCounts])

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
