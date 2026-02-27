import type { ArticleSummary } from '../types'
import { ArticleDetail } from './ArticleDetail'

interface ArticleRowProps {
  article: ArticleSummary
  isExpanded: boolean
  onToggle: () => void
  onDelete: (articleId: string, title: string, chunkCount: number) => void
}

function formatRelativeDate(dateStr: string | null): string {
  if (!dateStr) return 'Unknown'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return '1d ago'
  if (diffDays < 7) return `${diffDays}d ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`
  return `${Math.floor(diffDays / 365)}y ago`
}

function truncateTitle(title: string, max: number = 60): string {
  return title.length > max ? title.slice(0, max) + '...' : title
}

const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg
    className={`row-chevron${open ? ' open' : ''}`}
    width="12"
    height="12"
    viewBox="0 0 12 12"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    aria-hidden="true"
  >
    <path d="M3 4.5 6 7.5 9 4.5" />
  </svg>
)

export function ArticleRow({ article, isExpanded, onToggle, onDelete }: ArticleRowProps): React.ReactElement {
  return (
    <div className={`article-row-wrapper${isExpanded ? ' expanded' : ''}`}>
      <button
        type="button"
        className="article-row"
        onClick={onToggle}
        aria-expanded={isExpanded}
        aria-label={`${article.title}, ${article.chunk_count} parts, ${formatRelativeDate(article.imported_at)}`}
      >
        <span className={`source-badge source-${article.source_type}`}>
          {article.source_type.toUpperCase()}
        </span>
        <span className="article-row-title" title={article.title}>
          {truncateTitle(article.title)}
        </span>
        <span className="article-row-parts">{article.chunk_count} parts</span>
        <span className="article-row-date">{formatRelativeDate(article.imported_at)}</span>
        <ChevronIcon open={isExpanded} />
      </button>
      {isExpanded && (
        <ArticleDetail
          articleId={article.article_id}
          title={article.title}
          onDelete={onDelete}
        />
      )}
    </div>
  )
}
