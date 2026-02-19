import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
    local: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
  runtime: {
    sendMessage: vi.fn(),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
  },
})

describe('Accessibility attributes', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('ErrorBoundary copy button has aria-label', async () => {
    const { ErrorBoundary } = await import('../../src/sidebar/components/ErrorBoundary')
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

    const btn = container.querySelector('button')
    expect(btn).not.toBeNull()
    expect(btn!.getAttribute('aria-label')).toBe('Copy error details to clipboard')
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
})
