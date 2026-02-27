import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { managementApi } from '../api'
import { ConfirmDialog } from './ConfirmDialog'
import { showToast } from './Toast'

interface ArticleDetailProps {
  articleId: string
  title: string
  onDelete: (articleId: string, title: string, chunkCount: number) => void
}

export function ArticleDetail({ articleId, title, onDelete }: ArticleDetailProps): React.ReactElement {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [editingTags, setEditingTags] = useState(false)
  const [editTags, setEditTags] = useState<string[]>([])
  const [editTagInput, setEditTagInput] = useState('')
  const queryClient = useQueryClient()

  const { data: detail, isLoading } = useQuery({
    queryKey: ['article', articleId],
    queryFn: () => managementApi.getArticle(articleId),
  })

  const tagMutation = useMutation({
    mutationFn: () => managementApi.updateTags(articleId, editTags),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['article', articleId] })
      queryClient.invalidateQueries({ queryKey: ['articles'] })
      queryClient.invalidateQueries({ queryKey: ['tags'] })
      setEditingTags(false)
      showToast('Tags updated', 'success')
    },
    onError: () => {
      showToast('Failed to update tags', 'error')
    },
  })

  if (isLoading || !detail) {
    return (
      <div className="article-detail" aria-busy="true">
        <div className="skeleton detail-skeleton-line" />
        <div className="skeleton detail-skeleton-sub" />
        <div className="skeleton detail-skeleton-block" />
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
      <div className="article-detail-meta">
        <span className="article-detail-label">Tags:</span>
        {!editingTags ? (
          <>
            <div className="tag-pills">
              {(detail.tags ?? []).length > 0
                ? detail.tags!.map(t => <span key={t} className="tag-pill">{t}</span>)
                : <span className="article-detail-value tag-none">None</span>
              }
            </div>
            <button type="button" className="link-btn" onClick={() => {
              setEditTags(detail.tags ?? [])
              setEditingTags(true)
            }}>Edit</button>
          </>
        ) : (
          <div className="tag-editor-inline">
            <div className="tag-pills">
              {editTags.map(tag => (
                <span key={tag} className="tag-pill">
                  {tag}
                  <button type="button" className="tag-pill-remove"
                    onClick={() => setEditTags(prev => prev.filter(t => t !== tag))}
                    aria-label={`Remove tag ${tag}`}>&times;</button>
                </span>
              ))}
            </div>
            <input
              type="text"
              className="tag-input"
              placeholder="Add tag..."
              value={editTagInput}
              onChange={e => setEditTagInput(e.target.value)}
              onKeyDown={e => {
                if ((e.key === 'Enter' || e.key === ',') && editTagInput.trim()) {
                  e.preventDefault()
                  const newTag = editTagInput.trim().replace(/,$/g, '')
                  if (newTag && !editTags.includes(newTag) && editTags.length < 20) {
                    setEditTags(prev => [...prev, newTag])
                  }
                  setEditTagInput('')
                }
              }}
              onPaste={e => {
                const pasted = e.clipboardData.getData('text')
                if (pasted.includes(',')) {
                  e.preventDefault()
                  const newTags = pasted.split(',').map(t => t.trim()).filter(Boolean)
                  setEditTags(prev => {
                    const combined = [...prev, ...newTags.filter(t => !prev.includes(t))]
                    return combined.slice(0, 20)
                  })
                  setEditTagInput('')
                }
              }}
              maxLength={100}
            />
            <div className="tag-editor-actions">
              <button type="button" className="primary-btn" onClick={() => tagMutation.mutate()}
                disabled={tagMutation.isPending}>
                {tagMutation.isPending ? 'Saving\u2026' : 'Save'}
              </button>
              <button type="button" className="secondary-btn" onClick={() => setEditingTags(false)}>Cancel</button>
            </div>
          </div>
        )}
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
