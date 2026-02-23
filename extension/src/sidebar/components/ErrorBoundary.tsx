import React from 'react'

interface Props {
  children: React.ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  private handleCopyError = () => {
    if (this.state.error) {
      navigator.clipboard.writeText(this.state.error.stack ?? this.state.error.message).catch(() => {})
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 flex flex-col gap-3 error-fallback" role="alert">
          <p className="title">Something went wrong</p>
          <p className="detail">
            {this.state.error?.message ?? 'An unexpected error occurred.'}
          </p>
          <p className="hint">
            Try refreshing the page. If the issue persists, copy the error and report it.
          </p>
          <button
            onClick={this.handleCopyError}
            style={{ background: 'none', border: 'none', padding: 0, color: 'var(--accent)', textDecoration: 'underline', cursor: 'pointer', fontSize: '0.72rem', textAlign: 'left' }}
            aria-label="Copy error details to clipboard"
          >
            Copy error details
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
