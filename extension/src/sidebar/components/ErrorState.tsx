import React from 'react'

interface ErrorStateProps {
  message: string
  title?: string
  onRetry?: () => void
}

export function ErrorState({ message, title, onRetry }: ErrorStateProps): React.ReactElement {
  return (
    <div
      className="alert-banner error"
      role="alert"
      aria-live="assertive"
    >
      <p className="alert-title">{title ?? 'Error'}</p>
      <p className="alert-message">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="link-btn"
          aria-label="Retry generating reply"
        >
          Try again
        </button>
      )}
    </div>
  )
}
