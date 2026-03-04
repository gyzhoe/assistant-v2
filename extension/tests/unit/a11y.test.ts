import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
  runtime: {
    sendMessage: vi.fn().mockResolvedValue(undefined),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
  },
})

// Mock matchMedia for useTheme (jsdom doesn't implement it)
vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))

describe('Accessibility attributes', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('ErrorBoundary copy button has aria-label', async () => {
    const { ErrorBoundary } = await import('../../src/shared/components/ErrorBoundary')
    const React = await import('react')
    const { render } = await import('@testing-library/react')

    // Trigger an error boundary
    function Boom(): React.ReactElement {
      throw new Error('test crash')
    }
    // Suppress console.error from error boundary
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { container } = render(
      React.createElement(ErrorBoundary, null, React.createElement(Boom))
    )
    spy.mockRestore()

    const buttons = container.querySelectorAll('button')
    expect(buttons.length).toBeGreaterThanOrEqual(2)
    const retryBtn = buttons[0]
    const copyBtn = buttons[1]
    expect(retryBtn.getAttribute('aria-label')).toBe('Try again')
    expect(copyBtn.getAttribute('aria-label')).toBe('Copy error details to clipboard')
  })

  it('ErrorState retry button has aria-label', async () => {
    const { ErrorState } = await import('../../src/sidebar/components/ErrorState')
    const React = await import('react')
    const { render } = await import('@testing-library/react')

    const { container } = render(
      React.createElement(ErrorState, { message: 'fail', onRetry: vi.fn() })
    )
    const btn = container.querySelector('button')
    expect(btn).not.toBeNull()
    expect(btn!.getAttribute('aria-label')).toBe('Retry generating reply')
  })

  it('SkeletonLoader has role=status and aria-live', async () => {
    const { SkeletonLoader } = await import('../../src/sidebar/components/SkeletonLoader')
    const React = await import('react')
    const { render } = await import('@testing-library/react')

    const { container } = render(React.createElement(SkeletonLoader))
    const el = container.firstElementChild!
    expect(el.getAttribute('role')).toBe('status')
    expect(el.getAttribute('aria-live')).toBe('polite')
    expect(el.getAttribute('aria-label')).toBe('Generating reply, please wait')
  })

  it('ThemeToggle button has correct aria-label', async () => {
    const { ThemeToggle } = await import('../../src/sidebar/components/ThemeToggle')
    const React = await import('react')
    const { render } = await import('@testing-library/react')

    const { container } = render(
      React.createElement(ThemeToggle, {
        theme: 'dark',
        resolvedTheme: 'dark',
        onCycle: vi.fn(),
      })
    )
    const btn = container.querySelector('button')
    expect(btn).not.toBeNull()
    expect(btn!.getAttribute('aria-label')).toBe('Switch theme, current: dark')
  })

  it('App root has data-theme attribute', async () => {
    // useTheme depends on useSettings which reads chrome.storage
    const App = (await import('../../src/sidebar/App')).default
    const React = await import('react')
    const { render } = await import('@testing-library/react')

    const { container } = render(React.createElement(App))
    const shell = container.querySelector('[data-theme]')
    expect(shell).not.toBeNull()
    expect(['light', 'dark']).toContain(shell!.getAttribute('data-theme'))
  })
})
