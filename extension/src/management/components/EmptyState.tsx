interface EmptyStateProps {
  onImportClick: () => void
}

export function EmptyState({ onImportClick }: EmptyStateProps): React.ReactElement {
  return (
    <div className="empty-state">
      <svg className="empty-state-icon" width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
        <rect x="6" y="4" width="36" height="40" rx="3" />
        <path d="M14 16h20M14 24h16M14 32h12" />
      </svg>
      <h3 className="empty-state-title">No articles yet</h3>
      <p className="empty-state-desc">
        Import knowledge base documents to get started. Supported formats: PDF, HTML, JSON, CSV, or import from a URL.
      </p>
      <button
        type="button"
        className="primary-btn"
        onClick={onImportClick}
      >
        Import Your First Article
      </button>
    </div>
  )
}
