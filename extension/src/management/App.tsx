import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { managementApi, ApiError, checkSession, login } from './api'
import { Header } from './components/Header'
import { StatCards } from './components/StatCards'
import { ArticleList } from './components/ArticleList'
import { ImportSection } from './components/ImportSection'
import { ArticleEditor } from './components/ArticleEditor'
import { TokenGate } from './components/TokenGate'
import { ToastContainer } from '@/shared/components/Toast'
import { ErrorBoundary } from '@/shared/components/ErrorBoundary'

type ThemeMode = 'light' | 'dark'

function getSystemTheme(): ThemeMode {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function App(): React.ReactElement {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem('kb-manage-theme')
    return saved === 'dark' || saved === 'light' ? saved : getSystemTheme()
  })
  const [needsAuth, setNeedsAuth] = useState(false)
  const [sessionChecked, setSessionChecked] = useState(false)
  const [authErrorMessage, setAuthErrorMessage] = useState<string | undefined>(undefined)
  const [authKey, setAuthKey] = useState(0)
  const [importOpen, setImportOpen] = useState(false)
  const [view, setView] = useState<'list' | 'create' | 'edit'>('list')
  const [editArticleId, setEditArticleId] = useState<string | null>(null)
  const importNodeRef = useRef<HTMLDivElement | null>(null)

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark'
      localStorage.setItem('kb-manage-theme', next)
      return next
    })
  }, [])

  // Check existing session cookie on mount; auto-login from localhost
  useEffect(() => {
    checkSession()
      .then(async valid => {
        if (valid) {
          setNeedsAuth(false)
          setSessionChecked(true)
          return
        }
        // Auto-login from localhost (backend allows token-less login for local access)
        const ok = await login('').catch(() => false)
        setNeedsAuth(!ok)
        setSessionChecked(true)
      })
      .catch(() => {
        setNeedsAuth(true)
        setSessionChecked(true)
      })
  }, [])

  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery({
    queryKey: ['stats', authKey],
    queryFn: () => managementApi.getStats(),
    staleTime: 60_000,
    retry: false,
    enabled: sessionChecked && !needsAuth,
  })

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ['health', authKey],
    queryFn: () => managementApi.getHealth(),
    staleTime: 60_000,
    retry: false,
    enabled: sessionChecked && !needsAuth,
  })

  // Check for 401 on stats — session may have expired
  useEffect(() => {
    if (statsError instanceof ApiError && statsError.status === 401) {
      setNeedsAuth(true)
    }
  }, [statsError])

  const handleAuthenticated = useCallback(() => {
    setNeedsAuth(false)
    setAuthErrorMessage(undefined)
    setAuthKey(prev => prev + 1) // re-trigger queries
  }, [])

  const handleAuthRequired = useCallback((message?: string) => {
    setNeedsAuth(true)
    setAuthErrorMessage(message)
  }, [])

  const importRefCallback = useCallback((node: HTMLDivElement | null) => {
    importNodeRef.current = node
  }, [])

  const handleImportClick = useCallback(() => {
    setImportOpen(true)
    // Wait for render, then scroll
    requestAnimationFrame(() => {
      importNodeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }, [])

  const handleNewArticle = useCallback(() => setView('create'), [])
  const handleBackToList = useCallback(() => { setView('list'); setEditArticleId(null) }, [])
  const handleEditArticle = useCallback((id: string) => {
    setEditArticleId(id)
    setView('edit')
  }, [])

  if (!sessionChecked) {
    return (
      <div className="app-shell" data-theme={theme}>
        <Header theme={theme} onToggleTheme={toggleTheme} onImportClick={handleImportClick} />
      </div>
    )
  }

  if (needsAuth) {
    return (
      <div className="app-shell" data-theme={theme}>
        <Header theme={theme} onToggleTheme={toggleTheme} onImportClick={handleImportClick} />
        <TokenGate onAuthenticated={handleAuthenticated} errorMessage={authErrorMessage} />
      </div>
    )
  }

  return (
    <div className="app-shell" data-theme={theme}>
      <ErrorBoundary>
        <Header
          theme={theme}
          onToggleTheme={toggleTheme}
          onImportClick={handleImportClick}
          onNewArticle={handleNewArticle}
          showNewArticle={view === 'list'}
        />
        {view === 'create' ? (
          <main className="mgmt-main">
            <ArticleEditor onBack={handleBackToList} />
          </main>
        ) : view === 'edit' && editArticleId ? (
          <main className="mgmt-main">
            <ArticleEditor onBack={handleBackToList} mode="edit" articleId={editArticleId} />
          </main>
        ) : (
          <main className="mgmt-main">
            <StatCards stats={stats} health={health} isLoading={statsLoading || healthLoading} />
            <ArticleList onImportClick={handleImportClick} onAuthRequired={handleAuthRequired} onEditArticle={handleEditArticle} />
            <ImportSection
              isOpen={importOpen}
              onToggle={() => setImportOpen(prev => !prev)}
              sectionRef={importRefCallback}
            />
          </main>
        )}
      </ErrorBoundary>
      <ToastContainer />
    </div>
  )
}
