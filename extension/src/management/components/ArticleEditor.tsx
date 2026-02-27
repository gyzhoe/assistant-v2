import { useState, useRef, useEffect, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { managementApi, ApiError } from '../api'
import { showToast } from './Toast'

interface ArticleEditorProps {
  onBack: () => void
}

export function ArticleEditor({ onBack }: ArticleEditorProps): React.ReactElement {
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [error, setError] = useState('')
  const titleRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const isDirty = title.length > 0 || content.length > 0

  // Auto-focus title on mount
  useEffect(() => {
    titleRef.current?.focus()
  }, [])

  const mutation = useMutation({
    mutationFn: () => managementApi.createArticle(title.trim(), content.trim()),
    onSuccess: (data) => {
      showToast(`Article created — ${data.chunks_ingested} chunks ingested`, 'success')
      queryClient.invalidateQueries({ queryKey: ['articles'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      onBack()
    },
    onError: (err: Error) => {
      if (err instanceof ApiError && err.status === 409) {
        setError('An article with this title already exists.')
      } else if (err instanceof ApiError && err.status === 503) {
        setError('Embedding service (Ollama) is unavailable. Is it running?')
      } else {
        setError('Failed to create article. Please try again.')
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
      if (!window.confirm('You have unsaved changes. Discard them?')) return
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

  const canSave = title.trim().length > 0 && content.trim().length > 0 && !mutation.isPending

  return (
    <div className="editor-container">
      <div className="editor-header">
        <button type="button" className="secondary-btn" onClick={handleCancel}>
          <BackIcon /> Back
        </button>
        <h2 className="editor-title">Create New Article</h2>
        <button
          type="button"
          className="primary-btn"
          onClick={handleSave}
          disabled={!canSave}
        >
          {mutation.isPending ? 'Saving\u2026' : 'Save Article'}
        </button>
      </div>

      <div className="editor-fields">
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
          />
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
          />
          <p className="editor-hint">
            Use <code>##</code> headings to split into sections for better search results.
          </p>
        </div>

        {error && <p className="editor-error" role="alert">{error}</p>}
      </div>
    </div>
  )
}

const BackIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M8.5 2.5L4 7l4.5 4.5" />
  </svg>
)
