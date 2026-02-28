import { showToast } from './Toast'

interface HeaderProps {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  onImportClick: () => void
  onNewArticle?: () => void
  showNewArticle?: boolean
}

const SunIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" aria-hidden="true">
    <circle cx="8" cy="8" r="3" />
    <path d="M8 1.5v1M8 13.5v1M1.5 8h1M13.5 8h1M3.4 3.4l.7.7M11.9 11.9l.7.7M3.4 12.6l.7-.7M11.9 4.1l.7-.7" />
  </svg>
)

const MoonIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" aria-hidden="true">
    <path d="M13.2 9.8A5.5 5.5 0 1 1 6.2 2.8a4.4 4.4 0 0 0 7 7Z" />
  </svg>
)

const GearIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6.86 2h2.28l.32 1.6a5 5 0 0 1 1.18.68l1.56-.52.98 1.7-1.24 1.08a5 5 0 0 1 0 1.36l1.24 1.08-.98 1.7-1.56-.52a5 5 0 0 1-1.18.68L9.14 14H6.86l-.32-1.6a5 5 0 0 1-1.18-.68l-1.56.52-.98-1.7 1.24-1.08a5 5 0 0 1 0-1.36L2.82 7.02l.98-1.7 1.56.52a5 5 0 0 1 1.18-.68L6.86 2z" />
    <circle cx="8" cy="8.5" r="1.8" />
  </svg>
)

const PlusIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    <path d="M7 2v10M2 7h10" />
  </svg>
)

const PencilIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10 2l2 2-8 8H2v-2l8-8z" />
  </svg>
)

export function Header({ theme, onToggleTheme, onImportClick, onNewArticle, showNewArticle }: HeaderProps): React.ReactElement {
  return (
    <header className="mgmt-header">
      <div className="mgmt-header-left">
        <div className="brand-mark" aria-hidden="true">AI</div>
        <h1 className="mgmt-title">Knowledge Base Management</h1>
      </div>
      <div className="mgmt-header-right">
        {showNewArticle && onNewArticle && (
          <button
            type="button"
            className="secondary-btn mgmt-new-article-btn"
            onClick={onNewArticle}
          >
            <PencilIcon />
            New Article
          </button>
        )}
        <button
          type="button"
          className="primary-btn mgmt-import-btn"
          onClick={onImportClick}
        >
          <PlusIcon />
          Import
        </button>
        <button
          type="button"
          className="theme-toggle mgmt-settings-btn"
          onClick={() => {
            showToast('Right-click the extension icon in the toolbar \u2192 Extension options', 'info')
          }}
          aria-label="Extension settings"
          title="Extension settings"
        >
          <GearIcon />
        </button>
        <button
          type="button"
          className="theme-toggle"
          onClick={onToggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          title={`Current theme: ${theme}`}
        >
          {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
        </button>
      </div>
    </header>
  )
}
