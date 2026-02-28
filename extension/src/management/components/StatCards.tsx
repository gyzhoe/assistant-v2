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
            <div className="skeleton stat-label-skeleton" />
            <div className="skeleton stat-value-skeleton" />
          </div>
        ))}
      </div>
    )
  }

  const systemOk = health?.status === 'ok'

  return (
    <div className="stat-cards">
      <div className="stat-card">
        <span className="stat-label">Articles</span>
        <span className="stat-value">{stats?.total_articles ?? 0}</span>
      </div>
      <div className="stat-card">
        <span className="stat-label">Parts</span>
        <span className="stat-value">{stats?.total_chunks ?? 0}</span>
      </div>
      <div className="stat-card">
        <span className={`stat-indicator ${systemOk ? 'ok' : 'error'}`} />
        <span className="stat-value stat-status-value">
          {systemOk ? 'Online' : 'Degraded'}
        </span>
      </div>
    </div>
  )
}
