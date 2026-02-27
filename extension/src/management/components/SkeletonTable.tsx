interface SkeletonTableProps {
  rows?: number
}

export function SkeletonTable({ rows = 5 }: SkeletonTableProps): React.ReactElement {
  return (
    <div className="skeleton-table" aria-busy="true" aria-label="Loading articles">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row">
          <div className="skeleton skeleton-badge" />
          <div className="skeleton-row-content">
            <div className="skeleton skeleton-title" />
            <div className="skeleton skeleton-meta" />
          </div>
          <div className="skeleton skeleton-count" />
          <div className="skeleton skeleton-date" />
        </div>
      ))}
    </div>
  )
}
