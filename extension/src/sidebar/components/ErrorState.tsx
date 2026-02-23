import React from 'react'

interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps): React.ReactElement {
  return (
    <div
      className="alert-banner error"
      role="alert"
      aria-live="assertive"
    >
      <p style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Error</p>
      <p style={{ marginBottom: '0.5rem' }}>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{ background: 'none', border: 'none', padding: 0, color: 'var(--accent)', textDecoration: 'underline', cursor: 'pointer', fontSize: 'inherit' }}
          aria-label="Retry generating reply"
        >
          Try again
        </button>
      )}
    </div>
  )
}
