import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { managementApi } from '../api'
import { ConfirmDialog } from './ConfirmDialog'

interface ArticleDetailProps {
  articleId: string
  title: string
  onDelete: (articleId: string, title: string, chunkCount: number) => void
}

export function ArticleDetail({ articleId, title, onDelete }: ArticleDetailProps): React.ReactElement {
  const [confirmOpen, setConfirmOpen] = useState(false)

  const { data: detail, isLoading } = useQuery({
    queryKey: ['article', articleId],
    queryFn: () => managementApi.getArticle(articleId),
  })

  if (isLoading || !detail) {
    return (
      <div className="article-detail" aria-busy="true">
        <div className="skeleton" style={{ height: '1rem', width: '60%' }} />
        <div className="skeleton" style={{ height: '1rem', width: '40%', marginTop: '0.5rem' }} />
        <div className="skeleton" style={{ height: '3rem', width: '100%', marginTop: '0.5rem' }} />
      </div>
    )
  }

  const previewText = detail.chunks[0]?.text ?? ''
  const truncatedPreview = previewText.length > 200 ? previewText.slice(0, 200) + '...' : previewText

  const importDate = detail.imported_at
    ? new Date(detail.imported_at).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : 'Unknown'

  return (
    <div className="article-detail">
      <div className="article-detail-meta">
        <span className="article-detail-label">Source:</span>
        <span className="article-detail-value">{detail.source} ({detail.source_type.toUpperCase()})</span>
      </div>
      <div className="article-detail-meta">
        <span className="article-detail-label">Parts:</span>
        <span className="article-detail-value">{detail.chunk_count}</span>
        <span className="article-detail-sep">|</span>
        <span className="article-detail-label">Imported:</span>
        <span className="article-detail-value">{importDate}</span>
      </div>
      {truncatedPreview && (
        <div className="article-detail-preview">
          <span className="article-detail-label">Preview:</span>
          <p className="article-preview-text">&ldquo;{truncatedPreview}&rdquo;</p>
        </div>
      )}
      <div className="article-detail-actions">
        <button
          type="button"
          className="primary-btn confirm-danger"
          onClick={() => setConfirmOpen(true)}
        >
          Delete Article
        </button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="Delete Article"
        description={`Delete "${title}" and its ${detail.chunk_count} parts? This cannot be undone.`}
        onConfirm={() => {
          setConfirmOpen(false)
          onDelete(articleId, title, detail.chunk_count)
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}
