import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the api module's setToken
const mockSetToken = vi.fn()
vi.mock('../../src/management/api', () => ({
  setToken: (...args: unknown[]) => mockSetToken(...args),
}))

// Mock sessionStorage (needed for module import)
vi.stubGlobal('sessionStorage', {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
})

describe('TokenGate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })

  it('renders form with input and submit button', async () => {
    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { TokenGate } = await import('../../src/management/components/TokenGate')

    const { container } = render(React.createElement(TokenGate, { onAuthenticated: vi.fn() }))

    const input = container.querySelector('input[type="password"]')
    const button = container.querySelector('button[type="submit"]')
    expect(input).not.toBeNull()
    expect(button).not.toBeNull()
    expect(button!.textContent).toContain('Authenticate')
  })

  it('shows error message on empty submit', async () => {
    const React = await import('react')
    const { render, fireEvent } = await import('@testing-library/react')
    const { TokenGate } = await import('../../src/management/components/TokenGate')

    const onAuth = vi.fn()
    const { container } = render(React.createElement(TokenGate, { onAuthenticated: onAuth }))

    const form = container.querySelector('form')!
    fireEvent.submit(form)

    // "Token is required" error should appear
    const error = container.querySelector('.token-gate-error')
    expect(error).not.toBeNull()
    expect(error!.textContent).toContain('Token is required')
    expect(onAuth).not.toHaveBeenCalled()
  })

  it('calls onAuthenticated with valid token', async () => {
    const React = await import('react')
    const { render, fireEvent } = await import('@testing-library/react')
    const { TokenGate } = await import('../../src/management/components/TokenGate')

    const onAuth = vi.fn()
    const { container } = render(React.createElement(TokenGate, { onAuthenticated: onAuth }))

    const input = container.querySelector('input[type="password"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'valid-token' } })

    const form = container.querySelector('form')!
    fireEvent.submit(form)

    expect(mockSetToken).toHaveBeenCalledWith('valid-token')
    expect(onAuth).toHaveBeenCalledOnce()
  })

  it('displays external errorMessage prop', async () => {
    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { TokenGate } = await import('../../src/management/components/TokenGate')

    const { container } = render(
      React.createElement(TokenGate, {
        onAuthenticated: vi.fn(),
        errorMessage: 'Invalid token',
      })
    )

    const alerts = container.querySelectorAll('[role="alert"]')
    const errorTexts = Array.from(alerts).map((el) => el.textContent)
    expect(errorTexts).toContain('Invalid token')
  })
})
