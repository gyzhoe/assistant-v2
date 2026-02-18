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
        <div className="p-4 flex flex-col gap-3" role="alert">
          <p className="font-semibold text-red-700">Something went wrong</p>
          <p className="text-neutral-600 text-xs">
            {this.state.error?.message ?? 'An unexpected error occurred.'}
          </p>
          <p className="text-neutral-500 text-xs">
            Try refreshing the page. If the issue persists, copy the error and report it.
          </p>
          <button
            onClick={this.handleCopyError}
            className="text-xs underline text-accent hover:text-accent-dark text-left"
          >
            Copy error details
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
