import { useState } from 'react'
import { login } from '../api'

interface TokenGateProps {
  onAuthenticated: () => void
  errorMessage?: string
}

export function TokenGate({ onAuthenticated, errorMessage }: TokenGateProps): React.ReactElement {
  const [value, setValue] = useState('')
  const [error, setError] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) {
      setError(true)
      return
    }
    setError(false)
    setLoginError('')
    setSubmitting(true)
    try {
      const ok = await login(trimmed)
      if (ok) {
        onAuthenticated()
      } else {
        setLoginError('Invalid API token.')
      }
    } catch {
      setLoginError('Login failed. Is the backend running?')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="token-gate">
      <div className="token-gate-card">
        <div className="token-gate-icon" aria-hidden="true">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <rect x="3" y="11" width="18" height="11" rx="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </div>
        <h2 className="token-gate-title">Authentication Required</h2>
        <p className="token-gate-desc">Enter the API token to access KB management.</p>
        {errorMessage && <p className="token-gate-error" role="alert">{errorMessage}</p>}
        {loginError && <p className="token-gate-error" role="alert">{loginError}</p>}
        <form onSubmit={handleSubmit} className="token-gate-form">
          <input
            type="password"
            className={`token-gate-input${error ? ' token-gate-input-error' : ''}`}
            value={value}
            onChange={e => { setValue(e.target.value); setError(false); setLoginError('') }}
            placeholder="API token"
            autoFocus
            autoComplete="off"
            disabled={submitting}
          />
          {error && <p className="token-gate-error">Token is required</p>}
          <button type="submit" className="primary-btn token-gate-submit" disabled={submitting}>
            {submitting ? 'Authenticating...' : 'Authenticate'}
          </button>
        </form>
      </div>
    </div>
  )
}
