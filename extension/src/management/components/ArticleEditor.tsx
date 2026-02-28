import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { managementApi, ApiError } from '../api'
import { ConfirmDialog } from './ConfirmDialog'
import { showToast } from './Toast'
import { DEFAULT_TAG_SUGGESTIONS } from '../constants/tagSuggestions'
import type { ArticleDetail, CreateArticleResponse, UpdateArticleResponse } from '../types'

const CONTENT_TEMPLATE = `## Problem
Describe the issue or question this article addresses.

## Solution
Step-by-step instructions to resolve the problem.

1. First step
2. Second step
3. Third step

## Additional Notes
Any extra context, caveats, or related links.
`

/** Reconstruct markdown content from article chunks. */
function reconstructContent(detail: ArticleDetail): string {
  return detail.chunks.map(chunk => {
    const section = chunk.section ?? ''
    const text = chunk.text ?? ''
    if (section === 'Introduction' || !section) return text
    return `## ${section}\n\n${text}`
  }).join('\n\n')
}

interface ArticleEditorProps {
  onBack: () => void
  mode?: 'create' | 'edit'
  articleId?: string
}

export function ArticleEditor({ onBack, mode = 'create', articleId }: ArticleEditorProps): React.ReactElement {
  const [title, setTitle] = useState('')
  const [content, setContent] = useState(mode === 'create' ? CONTENT_TEMPLATE : '')
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [error, setError] = useState('')
  const [showTagSuggestions, setShowTagSuggestions] = useState(false)
  const [showDiscardDialog, setShowDiscardDialog] = useState(false)
  const [tagTruncateWarning, setTagTruncateWarning] = useState(false)
  const [loaded, setLoaded] = useState(mode === 'create')
  const titleRef = useRef<HTMLInputElement>(null)
  const originalRef = useRef<{ title: string; content: string; tags: string[] }>({ title: '', content: CONTENT_TEMPLATE, tags: [] })
  const queryClient = useQueryClient()

  const isEdit = mode === 'edit' && !!articleId

  // Fetch article detail in edit mode
  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['article', articleId],
    queryFn: () => managementApi.getArticle(articleId!),
    enabled: isEdit,
  })

  // Populate fields when article detail loads
  useEffect(() => {
    if (isEdit && detail) {
      const reconstructed = reconstructContent(detail)
      setTitle(detail.title)
      setContent(reconstructed)
      setTags(detail.tags ?? [])
      originalRef.current = { title: detail.title, content: reconstructed, tags: detail.tags ?? [] }
      setLoaded(true)
    }
  }, [isEdit, detail])

  const isDirty = isEdit
    ? title !== originalRef.current.title || content !== originalRef.current.content || JSON.stringify(tags) !== JSON.stringify(originalRef.current.tags)
    : title.length > 0 || (content !== CONTENT_TEMPLATE && content.length > 0) || tags.length > 0

  const { data: existingTags } = useQuery({
    queryKey: ['tags'],
    queryFn: () => managementApi.getTags(),
  })

  const tagSuggestions = useMemo(() => {
    const apiTags = existingTags?.tags ?? []
    return [...new Set([...DEFAULT_TAG_SUGGESTIONS, ...apiTags])]
      .filter(t => !tags.includes(t))
  }, [existingTags, tags])

  // Auto-focus title on mount (after loaded)
  useEffect(() => {
    if (loaded) titleRef.current?.focus()
  }, [loaded])

  const mutation = useMutation<CreateArticleResponse | UpdateArticleResponse, Error>({
    mutationFn: () =>
      isEdit
        ? managementApi.updateArticle(articleId!, title.trim(), content.trim(), tags)
        : managementApi.createArticle(title.trim(), content.trim(), tags),
    onSuccess: (data) => {
      if (isEdit) {
        const chunks = 'chunks_ingested' in data ? data.chunks_ingested : 0
        showToast(`Article updated — ${chunks} chunks re-indexed`, 'success')
        queryClient.invalidateQueries({ queryKey: ['article', articleId] })
      } else {
        const chunks = 'chunks_ingested' in data ? data.chunks_ingested : 0
        showToast(`Article created — ${chunks} chunks ingested`, 'success')
      }
      queryClient.invalidateQueries({ queryKey: ['articles'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['tags'] })
      onBack()
    },
    onError: (err: Error) => {
      if (err instanceof ApiError && err.status === 409) {
        setError('An article with this title already exists.')
      } else if (err instanceof ApiError && err.status === 403) {
        setError('Only manual articles can be edited.')
      } else if (err instanceof ApiError && err.status === 503) {
        setError('Embedding service (Ollama) is unavailable. Is it running?')
      } else {
        setError(isEdit ? 'Failed to update article. Please try again.' : 'Failed to create article. Please try again.')
      }
    },
  })

  const handleSave = useCallback(() => {
    if (!title.trim() || !content.trim() || mutation.isPending) return
    setError('')
    mutation.mutate()
  }, [title, content, mutation])

  const handleCancel = useCallback(() => {
    if (isDirty) {
      setShowDiscardDialog(true)
      return
    }
    onBack()
  }, [isDirty, onBack])

  // Ctrl+S / Cmd+S to save
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [handleSave])

  const canSave = title.trim().length > 0 && content.trim().length > 0 && !mutation.isPending && loaded
  const isNonManual = isEdit && detail && detail.source_type !== 'manual'

  if (isEdit && detailLoading) {
    return (
      <div className="editor-container">
        <div className="editor-header">
          <button type="button" className="secondary-btn" onClick={onBack}>
            <BackIcon /> Back
          </button>
          <h2 className="editor-title">Edit Article</h2>
          <button type="button" className="primary-btn" disabled>Save Article</button>
        </div>
        <div className="editor-fields">
          <div className="skeleton detail-skeleton-line" />
          <div className="skeleton detail-skeleton-block" />
        </div>
      </div>
    )
  }

  return (
    <div className="editor-container">
      <div className="editor-header">
        <button type="button" className="secondary-btn" onClick={handleCancel}>
          <BackIcon /> Back
        </button>
        <h2 className="editor-title">{isEdit ? 'Edit Article' : 'Create New Article'}</h2>
        <button
          type="button"
          className="primary-btn"
          onClick={handleSave}
          disabled={!canSave || !!isNonManual}
        >
          {mutation.isPending ? 'Saving\u2026' : 'Save Article'}
        </button>
      </div>

      <div className="editor-fields">
        {isNonManual && (
          <div className="editor-banner-warning" role="alert">
            Only manual articles can be edited. This article was imported from an external source.
          </div>
        )}
        <div className="editor-field">
          <label className="editor-label" htmlFor="article-title">Title</label>
          <input
            ref={titleRef}
            id="article-title"
            type="text"
            className="editor-input"
            placeholder="e.g., How to Reset Active Directory Passwords"
            value={title}
            onChange={e => { setTitle(e.target.value); setError('') }}
            maxLength={200}
            disabled={!!isNonManual}
          />
          {error && <p className="editor-error" role="alert">{error}</p>}
        </div>

        <div className="editor-field">
          <label className="editor-label" htmlFor="article-tags">Tags</label>
          <div className="tag-picker">
            <div className="tag-pills">
              {tags.map(tag => (
                <span key={tag} className="tag-pill">
                  {tag}
                  <button
                    type="button"
                    className="tag-pill-remove"
                    onClick={() => setTags(prev => prev.filter(t => t !== tag))}
                    aria-label={`Remove tag ${tag}`}
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
            <div className="tag-input-wrapper">
              <input
                id="article-tags"
                type="text"
                className="tag-input"
                list="tag-suggestions-editor"
                placeholder={tags.length >= 20 ? 'Max tags reached' : 'Add tags (e.g., NETWORK CONNECTION, MAILBOX)'}
                value={tagInput}
                onChange={e => setTagInput(e.target.value)}
                onKeyDown={e => {
                  if ((e.key === 'Enter' || e.key === ',') && tagInput.trim()) {
                    e.preventDefault()
                    const newTag = tagInput.trim().replace(/,$/g, '')
                    if (newTag && !tags.includes(newTag) && tags.length < 20) {
                      setTags(prev => [...prev, newTag])
                    }
                    setTagInput('')
                  }
                }}
                onPaste={e => {
                  const pasted = e.clipboardData.getData('text')
                  if (pasted.includes(',')) {
                    e.preventDefault()
                    const newTags = pasted.split(',').map(t => t.trim()).filter(Boolean)
                    setTags(prev => {
                      const combined = [...prev, ...newTags.filter(t => !prev.includes(t))]
                      if (combined.length > 20) {
                        setTagTruncateWarning(true)
                        setTimeout(() => setTagTruncateWarning(false), 3000)
                      }
                      return combined.slice(0, 20)
                    })
                    setTagInput('')
                  }
                }}
                disabled={tags.length >= 20}
                maxLength={100}
              />
              <datalist id="tag-suggestions-editor">
                {tagSuggestions.map(t => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </div>
          </div>
          {tagTruncateWarning && (
            <p className="editor-hint" style={{ color: 'var(--warn-text, #9a6700)' }}>Some pasted tags were truncated to the 20-tag limit.</p>
          )}
          <div className="tag-browse-row">
            <button
              type="button"
              className="tag-browse-toggle"
              onClick={() => setShowTagSuggestions(v => !v)}
              aria-expanded={showTagSuggestions}
              aria-label="Browse tag suggestions"
            >
              <svg
                width="10"
                height="10"
                viewBox="0 0 10 10"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                className={`tag-browse-chevron${showTagSuggestions ? ' open' : ''}`}
              >
                <path d="M3 2l4 3-4 3" />
              </svg>
              Browse request types
            </button>
            <span className="editor-hint">or type custom tags above</span>
          </div>
          {showTagSuggestions && (() => {
            const apiTags = existingTags?.tags ?? []
            const allSuggestions = [...new Set([...DEFAULT_TAG_SUGGESTIONS, ...apiTags])]
            return (
              <div className="tag-suggestions-list">
                {allSuggestions.map(t => {
                  const selected = tags.includes(t)
                  return (
                    <button
                      key={t}
                      type="button"
                      className={`tag-suggestion-chip ${selected ? 'tag-suggestion-selected' : ''}`}
                      onClick={() => {
                        if (selected) {
                          setTags(prev => prev.filter(x => x !== t))
                        } else if (tags.length < 20) {
                          setTags(prev => [...prev, t])
                        }
                      }}
                      disabled={!selected && tags.length >= 20}
                      aria-pressed={selected}
                    >
                      {selected ? '\u2713 ' : '+ '}{t}
                    </button>
                  )
                })}
              </div>
            )
          })()}
        </div>

        <div className="editor-field">
          <label className="editor-label" htmlFor="article-content">Content</label>
          <textarea
            id="article-content"
            className="editor-textarea"
            placeholder="Write your article in Markdown\u2026"
            value={content}
            onChange={e => setContent(e.target.value)}
            maxLength={100000}
            disabled={!!isNonManual}
          />
          <p className="editor-hint">
            Use <code>##</code> headings to split into sections for better search results.
          </p>
        </div>

      </div>

      <ConfirmDialog
        open={showDiscardDialog}
        title="Discard Changes"
        description="You have unsaved changes. Discard them?"
        confirmLabel="Discard"
        onConfirm={() => { setShowDiscardDialog(false); onBack() }}
        onCancel={() => setShowDiscardDialog(false)}
      />
    </div>
  )
}

const BackIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M8.5 2.5L4 7l4.5 4.5" />
  </svg>
)
