import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'

vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))
Element.prototype.scrollIntoView = vi.fn()

describe('SidebarToastContainer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  async function renderToastContainer() {
    const React = await import('react')
    const { render } = await import('@testing-library/react')
    const { SidebarToastContainer, showSidebarToast } = await import(
      '../../src/sidebar/components/Toast'
    )
    const result = render(React.createElement(SidebarToastContainer))
    return { result, showSidebarToast }
  }

  it('renders nothing when no toasts present', async () => {
    const { result } = await renderToastContainer()
    expect(result.container.querySelector('.sidebar-toast-container')).toBeNull()
  })

  it('shows a toast when showSidebarToast is called', async () => {
    const { result, showSidebarToast } = await renderToastContainer()

    await act(async () => {
      showSidebarToast('Test message', 'success')
    })

    const container = result.container.querySelector('.sidebar-toast-container')
    expect(container).not.toBeNull()
    expect(container?.textContent).toContain('Test message')
  })

  it('applies correct variant class for success type', async () => {
    const { result, showSidebarToast } = await renderToastContainer()

    await act(async () => {
      showSidebarToast('Success!', 'success')
    })

    const toast = result.container.querySelector('.sidebar-toast-success')
    expect(toast).not.toBeNull()
  })

  it('applies correct variant class for error type', async () => {
    const { result, showSidebarToast } = await renderToastContainer()

    await act(async () => {
      showSidebarToast('Error!', 'error')
    })

    const toast = result.container.querySelector('.sidebar-toast-error')
    expect(toast).not.toBeNull()
  })

  it('applies correct variant class for info type', async () => {
    const { result, showSidebarToast } = await renderToastContainer()

    await act(async () => {
      showSidebarToast('Info', 'info')
    })

    const toast = result.container.querySelector('.sidebar-toast-info')
    expect(toast).not.toBeNull()
  })

  it('auto-dismisses toast after 4 seconds', async () => {
    const { result, showSidebarToast } = await renderToastContainer()

    await act(async () => {
      showSidebarToast('Auto-dismiss me', 'info')
    })

    expect(result.container.querySelector('.sidebar-toast-container')).not.toBeNull()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })

    expect(result.container.querySelector('.sidebar-toast-container')).toBeNull()
  })

  it('closes toast when dismiss button is clicked', async () => {
    const { result, showSidebarToast } = await renderToastContainer()

    await act(async () => {
      showSidebarToast('Dismiss me', 'success')
    })

    const closeBtn = result.container.querySelector('.sidebar-toast-close') as HTMLButtonElement
    expect(closeBtn).not.toBeNull()

    await act(async () => {
      closeBtn.click()
    })

    expect(result.container.querySelector('.sidebar-toast-container')).toBeNull()
  })

  it('shows multiple toasts at once', async () => {
    const { result, showSidebarToast } = await renderToastContainer()

    await act(async () => {
      showSidebarToast('First', 'info')
      showSidebarToast('Second', 'success')
    })

    const toasts = result.container.querySelectorAll('.sidebar-toast')
    expect(toasts.length).toBe(2)
  })

  it('has aria-live and role for accessibility', async () => {
    const { result, showSidebarToast } = await renderToastContainer()

    await act(async () => {
      showSidebarToast('Accessible', 'info')
    })

    const container = result.container.querySelector('.sidebar-toast-container')
    expect(container?.getAttribute('aria-live')).toBe('polite')
    expect(container?.getAttribute('role')).toBe('status')
  })
})
