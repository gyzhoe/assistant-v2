import React, { useState, useEffect, useRef } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import { apiClient, ApiError } from '../../lib/api-client'
import { debugError, MAX_PINNED_ARTICLES } from '../../shared/constants'
import type { KBArticleListItem } from '../../shared/types'

const DEBOUNCE_MS = 300
const MIN_QUERY_LENGTH = 2

export function KBContextPicker(): React.ReactElement {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KBArticleListItem[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const pinnedArticles = useSidebarStore((s) => s.pinnedArticles)
  const pinArticle = useSidebarStore((s) => s.pinArticle)
  const unpinArticle = useSidebarStore((s) => s.unpinArticle)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (abortRef.current) abortRef.current.abort()

    if (query.trim().length < MIN_QUERY_LENGTH) {
      setResults([])
      setSearchError(null)
      return
    }

    const ctrl = new AbortController()
    abortRef.current = ctrl

    timerRef.current = setTimeout(async () => {
      setIsSearching(true)
      setSearchError(null)
      try {
        const resp = await apiClient.searchKBArticles(query.trim(), 5, 1, ctrl.signal)
        if (!ctrl.signal.aborted) {
          setResults(resp.articles)
        }
      } catch (err) {
        if (ctrl.signal.aborted) return
        debugError('KB search failed:', err)
        if (err instanceof ApiError) {
          setSearchError(`Search failed (${err.status})`)
        } else {
          setSearchError('Search failed')
        }
        setResults([])
      } finally {
        if (!ctrl.signal.aborted) {
          setIsSearching(false)
        }
      }
    }, DEBOUNCE_MS)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      ctrl.abort()
    }
  }, [query])

  const isPinned = (articleId: string) =>
    pinnedArticles.some((a) => a.article_id === articleId)

  const atPinCap = pinnedArticles.length >= MAX_PINNED_ARTICLES

  return (
    <div className="kb-picker" aria-label="Knowledge context picker">
      <span className="kb-picker-label">Knowledge Context</span>

      {/* Pinned chips */}
      {pinnedArticles.length > 0 && (
        <div className="kb-pinned" role="list" aria-label="Pinned articles">
          {pinnedArticles.map((article) => (
            <span key={article.article_id} className="kb-pin-chip" role="listitem">
              <span className="kb-pin-chip-title" title={article.title}>{article.title}</span>
              <button
                type="button"
                className="kb-pin-chip-remove"
                onClick={() => unpinArticle(article.article_id)}
                aria-label={`Unpin ${article.title}`}
              >
                &times;
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Pin cap warning */}
      {atPinCap && (
        <p className="support-text" role="status">Maximum {MAX_PINNED_ARTICLES} articles pinned</p>
      )}

      {/* Search input */}
      <input
        type="text"
        className="kb-search-input"
        placeholder="Search KB articles to add context..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Search KB articles"
      />

      {/* Status */}
      {isSearching && <p className="support-text">Searching&hellip;</p>}
      {searchError && <p className="support-text error-text">{searchError}</p>}

      {/* Results */}
      {results.length > 0 && (
        <div className="kb-results" role="list" aria-label="Search results">
          {results.map((article) => (
            <div key={article.article_id} className="kb-result-item" role="listitem">
              <span className="kb-result-title" title={article.title}>{article.title}</span>
              <span className="kb-result-source">{article.source_type}</span>
              <button
                type="button"
                className="kb-result-add"
                disabled={isPinned(article.article_id) || atPinCap}
                onClick={() => pinArticle({ article_id: article.article_id, title: article.title })}
                aria-label={
                  isPinned(article.article_id) ? `${article.title} already pinned` :
                  atPinCap ? `Maximum ${MAX_PINNED_ARTICLES} articles pinned` :
                  `Pin ${article.title}`
                }
                title={atPinCap && !isPinned(article.article_id) ? `Maximum ${MAX_PINNED_ARTICLES} articles pinned` : undefined}
              >
                {isPinned(article.article_id) ? '\u2713' : '+'}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isSearching && !searchError && results.length === 0 && query.trim().length >= MIN_QUERY_LENGTH && (
        <p className="support-text">No articles found</p>
      )}
    </div>
  )
}
