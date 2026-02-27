import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

// Stub scrollIntoView for jsdom
Element.prototype.scrollIntoView = vi.fn()

// Stub matchMedia for jsdom
vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))

// Mock crypto.randomUUID (used by Toast)
let uuidCounter = 0
vi.stubGlobal('crypto', {
  randomUUID: () => `uuid-${++uuidCounter}`,
})

// Mock the management API
const mockCreateArticle = vi.fn()
vi.mock('../../../src/management/api', () => ({
  managementApi: {
    createArticle: (...args: unknown[]) => mockCreateArticle(...args),
  },
  ApiError: class ApiError extends Error {
    status: number
    body: Record<string, unknown>
    constructor(status: number, body: Record<string, unknown> = {}) {
      super(`API error ${status}`)
      this.name = 'ApiError'
      this.status = status
      this.body = body
    }
  },
}))

// Import after mocks
import { ArticleEditor } from '../../../src/management/components/ArticleEditor'
import { ApiError } from '../../../src/management/api'

function renderEditor(onBack = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    onBack,
    ...render(
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(ArticleEditor, { onBack })
      )
    ),
  }
}

describe('ArticleEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    uuidCounter = 0
    document.body.innerHTML = ''
  })

  it('renders title input and content textarea', () => {
    renderEditor()
    expect(screen.getByLabelText('Title')).not.toBeNull()
    expect(screen.getByLabelText('Content')).not.toBeNull()
    expect(screen.getByText('Create New Article')).not.toBeNull()
  })

  it('save button is disabled when fields are empty', () => {
    renderEditor()
    const saveBtn = screen.getByRole('button', { name: /save article/i })
    expect(saveBtn.hasAttribute('disabled')).toBe(true)
  })

  it('save button is enabled when both fields are filled', () => {
    renderEditor()
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Test Title' } })
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'Test Content' } })
    const saveBtn = screen.getByRole('button', { name: /save article/i })
    expect(saveBtn.hasAttribute('disabled')).toBe(false)
  })

  it('cancel calls onBack when no changes', () => {
    const onBack = vi.fn()
    renderEditor(onBack)
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(onBack).toHaveBeenCalled()
  })

  it('cancel shows confirm dialog when there are changes', () => {
    const onBack = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderEditor(onBack)
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Draft' } })
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(confirmSpy).toHaveBeenCalledWith('You have unsaved changes. Discard them?')
    expect(onBack).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('successful save shows toast and calls onBack', async () => {
    const onBack = vi.fn()
    mockCreateArticle.mockResolvedValue({
      article_id: 'abc-123',
      title: 'My Article',
      chunks_ingested: 3,
      processing_time_ms: 150,
    })

    renderEditor(onBack)
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'My Article' } })
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'Some content here' } })
    fireEvent.click(screen.getByRole('button', { name: /save article/i }))

    await waitFor(() => {
      expect(onBack).toHaveBeenCalled()
    })
    expect(mockCreateArticle).toHaveBeenCalledWith('My Article', 'Some content here')
  })

  it('409 error displays duplicate title message', async () => {
    mockCreateArticle.mockRejectedValue(new ApiError(409))

    renderEditor()
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Duplicate' } })
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'Content' } })
    fireEvent.click(screen.getByRole('button', { name: /save article/i }))

    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert.textContent).toBe('An article with this title already exists.')
    })
  })
})
