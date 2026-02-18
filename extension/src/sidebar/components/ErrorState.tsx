import React from 'react'

interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps): React.ReactElement {
  return (
    <div
      className="mx-3 my-2 p-3 bg-red-50 border border-red-200 rounded text-sm"
      role="alert"
      aria-live="assertive"
    >
      <p className="font-semibold text-red-700 mb-1">Error</p>
      <p className="text-red-600 text-xs mb-2">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs text-accent hover:text-accent-dark underline"
        >
          Try again
        </button>
      )}
    </div>
  )
}
