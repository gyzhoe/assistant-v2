import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { managementApi, ApiError, getToken } from './api'
import { Header } from './components/Header'
import { StatCards } from './components/StatCards'
import { ArticleList } from './components/ArticleList'
import { ImportSection } from './components/ImportSection'
import { TokenGate } from './components/TokenGate'
import { ToastContainer } from './components/Toast'

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
  const [authKey, setAuthKey] = useState(0)
  const [importOpen, setImportOpen] = useState(false)
  const importNodeRef = useRef<HTMLDivElement | null>(null)

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark'
      localStorage.setItem('kb-manage-theme', next)
      return next
    })
  }, [])

  // Initial auth probe — if token already in sessionStorage, use it
  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery({
    queryKey: ['stats', authKey],
    queryFn: () => managementApi.getStats(),
    staleTime: 60_000,
    retry: false,
  })

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ['health', authKey],
    queryFn: () => managementApi.getHealth(),
    staleTime: 60_000,
    retry: false,
  })

  // Check for 401 on stats
  useEffect(() => {
    if (statsError instanceof ApiError && statsError.status === 401 && !getToken()) {
      setNeedsAuth(true)
    }
  }, [statsError])

  const handleAuthenticated = useCallback(() => {
    setNeedsAuth(false)
    setAuthKey(prev => prev + 1) // re-trigger queries
  }, [])

  const handleAuthRequired = useCallback(() => {
    setNeedsAuth(true)
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

  if (needsAuth) {
    return (
      <div className="app-shell" data-theme={theme}>
        <Header theme={theme} onToggleTheme={toggleTheme} onImportClick={handleImportClick} />
        <TokenGate onAuthenticated={handleAuthenticated} />
      </div>
    )
  }

  return (
    <div className="app-shell" data-theme={theme}>
      <Header theme={theme} onToggleTheme={toggleTheme} onImportClick={handleImportClick} />
      <main className="mgmt-main">
        <StatCards stats={stats} health={health} isLoading={statsLoading || healthLoading} />
        <ArticleList onImportClick={handleImportClick} onAuthRequired={handleAuthRequired} />
        <ImportSection
          isOpen={importOpen}
          onToggle={() => setImportOpen(prev => !prev)}
          sectionRef={importRefCallback}
        />
      </main>
      <ToastContainer />
    </div>
  )
}
