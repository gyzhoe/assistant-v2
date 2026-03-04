import { useState, useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { managementApi, ApiError } from '../api'
import type { SourceType, ArticleSummary } from '../types'
import { SearchBar } from './SearchBar'
import { SourceFilter } from './SourceFilter'
import { Pagination } from './Pagination'
import { ArticleRow } from './ArticleRow'
import { SkeletonTable } from './SkeletonTable'
import { EmptyState } from './EmptyState'
import { showToast } from '@/shared/components/Toast'

interface ArticleListProps {
  onImportClick: () => void
  onAuthRequired: (message?: string) => void
  onEditArticle?: (articleId: string) => void
}

const PAGE_SIZE = 20

export function ArticleList({ onImportClick, onAuthRequired, onEditArticle }: ArticleListProps): React.ReactElement {
  const [search, setSearch] = useState('')
  const [sourceType, setSourceType] = useState<SourceType | ''>('')
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const deleteTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const queryClient = useQueryClient()

  // Clear all pending delete timers on unmount
  useEffect(() => {
    const timers = deleteTimersRef.current
    return () => {
      for (const timer of timers.values()) clearTimeout(timer)
      timers.clear()
    }
  }, [])

  // Reset page when filters change
  useEffect(() => { setPage(1) }, [search, sourceType])

  const { data, isLoading, isFetching, isError, error } = useQuery({
    queryKey: ['articles', { page, search, source_type: sourceType }],
    queryFn: () => managementApi.listArticles({ page, page_size: PAGE_SIZE, search: search || undefined, source_type: sourceType || undefined }),
    placeholderData: (prev) => prev,
  })

  // Handle 401 at the query level
  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      onAuthRequired('Invalid token. Please try again.')
    }
  }, [error, onAuthRequired])

  const deleteMutation = useMutation({
    mutationFn: (articleId: string) => managementApi.deleteArticle(articleId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['articles'] })
      void queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  const handleDelete = useCallback((articleId: string, title: string, _chunkCount: number) => {
    setExpandedId(null)

    // Optimistic removal
    queryClient.setQueryData(
      ['articles', { page, search, source_type: sourceType }],
      (old: { articles: ArticleSummary[]; total_articles: number; page: number; page_size: number } | undefined) => {
        if (!old) return old
        return {
          ...old,
          articles: old.articles.filter(a => a.article_id !== articleId),
          total_articles: old.total_articles - 1,
        }
      }
    )

    // Delayed delete with undo support (8s to allow undo).
    // Uses a Map keyed by articleId so rapid deletions each get their own timer.
    const timer = setTimeout(() => {
      deleteTimersRef.current.delete(articleId)
      deleteMutation.mutate(articleId)
    }, 8000)
    deleteTimersRef.current.set(articleId, timer)

    showToast(`Deleted "${title}"`, 'success', {
      action: {
        label: 'Undo',
        onClick: () => {
          const t = deleteTimersRef.current.get(articleId)
          if (t) {
            clearTimeout(t)
            deleteTimersRef.current.delete(articleId)
          }
          void queryClient.invalidateQueries({ queryKey: ['articles'] })
          void queryClient.invalidateQueries({ queryKey: ['stats'] })
        },
      },
    })
  }, [page, search, sourceType, queryClient, deleteMutation])

  // Escape to close expanded row
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && expandedId) {
        setExpandedId(null)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [expandedId])

  // Prefetch on hover
  const handlePrefetch = useCallback((articleId: string) => {
    void queryClient.prefetchQuery({
      queryKey: ['article', articleId],
      queryFn: () => managementApi.getArticle(articleId),
      staleTime: 30_000,
    })
  }, [queryClient])

  if (isError && !(error instanceof ApiError && error.status === 401)) {
    return (
      <div className="alert-banner error" role="alert">
        <p className="alert-title">Connection error</p>
        <p className="alert-message">Unable to connect to the backend. Make sure the server is running at localhost:8765.</p>
      </div>
    )
  }

  const articles = data?.articles ?? []
  const totalArticles = data?.total_articles ?? 0
  const isEmpty = !isLoading && totalArticles === 0 && !search && !sourceType

  return (
    <div ref={listRef}>
      {!isEmpty && (
        <div className="article-toolbar">
          <SearchBar value={search} onChange={setSearch} />
          <SourceFilter value={sourceType} onChange={setSourceType} />
        </div>
      )}

      {isLoading && !data ? (
        <SkeletonTable />
      ) : isEmpty ? (
        <EmptyState onImportClick={onImportClick} />
      ) : articles.length === 0 ? (
        <div className="no-results">
          <p>No articles match your search.</p>
          <button
            type="button"
            className="link-btn"
            onClick={() => { setSearch(''); setSourceType('') }}
          >
            Clear filters
          </button>
        </div>
      ) : (
        <>
          <div className="article-rows" aria-busy={isFetching && !!data ? "true" : "false"}>
            {articles.map(article => (
              <div
                key={article.article_id}
                onMouseEnter={() => handlePrefetch(article.article_id)}
              >
                <ArticleRow
                  article={article}
                  isExpanded={expandedId === article.article_id}
                  onToggle={() => setExpandedId(prev => prev === article.article_id ? null : article.article_id)}
                  onDelete={handleDelete}
                  onEdit={onEditArticle}
                />
              </div>
            ))}
          </div>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={totalArticles}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  )
}
