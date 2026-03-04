import { DocumentIcon } from '../../shared/components/Icons'

interface EmptyStateProps {
  onImportClick: () => void
}

export function EmptyState({ onImportClick }: EmptyStateProps): React.ReactElement {
  return (
    <div className="empty-state">
      <span className="empty-state-icon"><DocumentIcon /></span>
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
