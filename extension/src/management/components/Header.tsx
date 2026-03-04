import { SunIcon, MoonIcon, PlusIcon, PencilIcon } from '../../shared/components/Icons'

interface HeaderProps {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  onImportClick: () => void
  onNewArticle?: () => void
  showNewArticle?: boolean
}

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
          className="secondary-btn mgmt-import-btn"
          onClick={onImportClick}
        >
          <PlusIcon />
          Import
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
