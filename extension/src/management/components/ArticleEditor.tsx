import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { managementApi, ApiError } from '../api'
import { showToast } from './Toast'

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

/** WHD request types shown as default tag suggestions (all 27 from WHD instance). */
const DEFAULT_TAG_SUGGESTIONS = [
  'ACCOUNT (u-,r-,b-number,...)',
  'ADMINISTRATIVE RIGHTS',
  'ARTICLE on LOAN',
  'CERTIFICATE ISSUE',
  'COLLABORATION/COMMUNICATION',
  'COMPUTER and ACCESSORIES',
  'FACILITEITEN',
  'FORWARD FROM IT DEPARTMENT',
  'REMOTE DESKTOP ACCESS',
  'IVANTI VPN',
  'LINUX',
  'MAILBOX (Outlook, Adm. Email...)',
  'Multi Factor Authentication (MFA)',
  'NEED A HARDPHONE (CAP)',
  'NEED A PHONE NUMBER',
  'NEED A SOFTPHONE (USB)',
  'NETWORK (Wired / Wireless)',
  'PERIPHERALS (keyboard, mouse, headset,...)',
  'PHONE ISSUE (General)',
  'PRINTER',
  'REDCAP',
  'REMOTE ACCESS',
  'Request by mail',
  'SHINY R App Hosting',
  'SOFTWARE',
  'SOFTWARE BLOCKED by AppLocker',
  'WEBSITE & WEB APPS',
]

interface ArticleEditorProps {
  onBack: () => void
}

export function ArticleEditor({ onBack }: ArticleEditorProps): React.ReactElement {
  const [title, setTitle] = useState('')
  const [content, setContent] = useState(CONTENT_TEMPLATE)
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [error, setError] = useState('')
  const [showTagSuggestions, setShowTagSuggestions] = useState(false)
  const titleRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const isDirty = title.length > 0 || (content !== CONTENT_TEMPLATE && content.length > 0) || tags.length > 0

  const { data: existingTags } = useQuery({
    queryKey: ['tags'],
    queryFn: () => managementApi.getTags(),
  })

  const tagSuggestions = useMemo(() => {
    const apiTags = existingTags?.tags ?? []
    return [...new Set([...DEFAULT_TAG_SUGGESTIONS, ...apiTags])]
      .filter(t => !tags.includes(t))
  }, [existingTags, tags])

  // Auto-focus title on mount
  useEffect(() => {
    titleRef.current?.focus()
  }, [])

  const mutation = useMutation({
    mutationFn: () => managementApi.createArticle(title.trim(), content.trim(), tags),
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
          <div className="tag-browse-row">
            <button
              type="button"
              className="tag-browse-toggle"
              onClick={() => setShowTagSuggestions(v => !v)}
              aria-expanded={showTagSuggestions}
            >
              {showTagSuggestions ? '\u25BE' : '\u25B8'} Browse request types
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
