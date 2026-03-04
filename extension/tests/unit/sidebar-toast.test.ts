import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'

vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))
Element.prototype.scrollIntoView = vi.fn()

describe('ToastContainer (shared)', () => {
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
    const { ToastContainer, showToast } = await import(
      '../../src/shared/components/Toast'
    )
    const result = render(React.createElement(ToastContainer))
    return { result, showToast }
  }

  it('renders nothing when no toasts present', async () => {
    const { result } = await renderToastContainer()
    expect(result.container.querySelector('.toast-container')).toBeNull()
  })

  it('shows a toast when showToast is called', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('Test message', 'success')
    })

    const container = result.container.querySelector('.toast-container')
    expect(container).not.toBeNull()
    expect(container?.textContent).toContain('Test message')
  })

  it('applies correct variant class for success type', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('Success!', 'success')
    })

    const toast = result.container.querySelector('.toast-success')
    expect(toast).not.toBeNull()
  })

  it('applies correct variant class for error type', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('Error!', 'error')
    })

    const toast = result.container.querySelector('.toast-error')
    expect(toast).not.toBeNull()
  })

  it('applies correct variant class for info type', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('Info', 'info')
    })

    const toast = result.container.querySelector('.toast-info')
    expect(toast).not.toBeNull()
  })

  it('auto-dismisses toast after 4 seconds', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('Auto-dismiss me', 'info')
    })

    expect(result.container.querySelector('.toast-container')).not.toBeNull()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })

    expect(result.container.querySelector('.toast-container')).toBeNull()
  })

  it('does not auto-dismiss a persistent toast', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('Stay visible', 'success', { persistent: true })
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000)
    })

    expect(result.container.querySelector('.toast-container')).not.toBeNull()
  })

  it('closes toast when dismiss button is clicked', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('Dismiss me', 'success')
    })

    const closeBtn = result.container.querySelector('.toast-close') as HTMLButtonElement
    expect(closeBtn).not.toBeNull()

    await act(async () => {
      closeBtn.click()
    })

    expect(result.container.querySelector('.toast-container')).toBeNull()
  })

  it('renders action button and calls callback on click', async () => {
    const { result, showToast } = await renderToastContainer()
    const onClick = vi.fn()

    await act(async () => {
      showToast('Undo delete', 'success', { action: { label: 'Undo', onClick } })
    })

    const actionBtn = result.container.querySelector('.toast-action') as HTMLButtonElement
    expect(actionBtn).not.toBeNull()
    expect(actionBtn.textContent).toBe('Undo')

    await act(async () => {
      actionBtn.click()
    })

    expect(onClick).toHaveBeenCalledOnce()
    // Toast should be dismissed after action
    expect(result.container.querySelector('.toast-container')).toBeNull()
  })

  it('shows multiple toasts at once', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('First', 'info')
      showToast('Second', 'success')
    })

    const toasts = result.container.querySelectorAll('.toast')
    expect(toasts.length).toBe(2)
  })

  it('has aria-live and role for accessibility', async () => {
    const { result, showToast } = await renderToastContainer()

    await act(async () => {
      showToast('Accessible', 'info')
    })

    const container = result.container.querySelector('.toast-container')
    expect(container?.getAttribute('aria-live')).toBe('polite')
    expect(container?.getAttribute('role')).toBe('status')
  })
})
