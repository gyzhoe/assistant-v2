import type { KBStats, HealthResponse } from '../types'

interface StatCardsProps {
  stats: KBStats | undefined
  health: HealthResponse | undefined
  isLoading: boolean
}

export function StatCards({ stats, health, isLoading }: StatCardsProps): React.ReactElement {
  if (isLoading) {
    return (
      <div className="stat-cards">
        {[0, 1, 2].map(i => (
          <div key={i} className="stat-card">
            <div className="skeleton stat-value-skeleton" />
            <div className="skeleton stat-label-skeleton" />
          </div>
        ))}
      </div>
    )
  }

  const systemOk = health?.status === 'ok'

  return (
    <div className="stat-cards">
      <div className="stat-card">
        <span className="stat-value">{stats?.total_articles ?? 0}</span>
        <span className="stat-label">Articles</span>
      </div>
      <div className="stat-card">
        <span className="stat-value">{stats?.total_chunks ?? 0}</span>
        <span className="stat-label">Parts</span>
      </div>
      <div className="stat-card">
        <span className={`stat-indicator ${systemOk ? 'ok' : 'error'}`} />
        <span className="stat-value stat-status-value">
          {systemOk ? 'All Online' : 'Degraded'}
        </span>
        <span className="stat-label">System Status</span>
      </div>
    </div>
  )
}
