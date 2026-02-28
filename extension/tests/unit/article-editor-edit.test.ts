import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { ArticleEditor } from '../../src/management/components/ArticleEditor'

// Mock the API module
vi.mock('../../src/management/api', () => ({
  managementApi: {
    getArticle: vi.fn(),
    getTags: vi.fn().mockResolvedValue({ tags: [] }),
    createArticle: vi.fn(),
    updateArticle: vi.fn(),
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

// Mock Toast
vi.mock('../../src/management/components/Toast', () => ({
  showToast: vi.fn(),
}))

// Stub scrollIntoView (jsdom doesn't have it)
Element.prototype.scrollIntoView = vi.fn()

import { managementApi } from '../../src/management/api'

function renderWithQuery(component: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    createElement(QueryClientProvider, { client: queryClient }, component),
  )
}

const mockArticleDetail = {
  article_id: 'art1',
  title: 'VPN Setup Guide',
  source_type: 'manual' as const,
  source: '',
  chunk_count: 2,
  imported_at: '2026-02-28T12:00:00+00:00',
  tags: ['NETWORK'],
  chunks: [
    { id: 'art1_chunk_0', text: 'Introduction text about VPN.', section: 'Introduction', metadata: {} },
    { id: 'art1_chunk_1', text: 'Step 1: Open settings.', section: 'Steps', metadata: {} },
  ],
}

describe('ArticleEditor — edit mode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(managementApi.getArticle).mockResolvedValue(mockArticleDetail)
    vi.mocked(managementApi.getTags).mockResolvedValue({ tags: ['NETWORK'] })
  })

  it('renders in edit mode with pre-filled data', async () => {
    renderWithQuery(
      createElement(ArticleEditor, { onBack: vi.fn(), mode: 'edit', articleId: 'art1' }),
    )

    // Wait for skeleton to resolve and form fields to appear
    await waitFor(() => {
      expect(screen.getByLabelText('Title')).toBeTruthy()
    })

    expect(screen.getByText('Edit Article')).toBeTruthy()

    const titleInput = screen.getByLabelText('Title') as HTMLInputElement
    expect(titleInput.value).toBe('VPN Setup Guide')

    const contentArea = screen.getByLabelText('Content') as HTMLTextAreaElement
    expect(contentArea.value).toContain('Introduction text about VPN.')
    expect(contentArea.value).toContain('## Steps')
  })

  it('calls updateArticle on save, not createArticle', async () => {
    vi.mocked(managementApi.updateArticle).mockResolvedValue({
      article_id: 'art1',
      title: 'VPN Setup Guide',
      chunks_created: 2,
      processing_time_ms: 50,
    })

    const onBack = vi.fn()
    const user = userEvent.setup()

    renderWithQuery(
      createElement(ArticleEditor, { onBack, mode: 'edit', articleId: 'art1' }),
    )

    // Wait for data to load
    await waitFor(() => {
      expect((screen.getByLabelText('Title') as HTMLInputElement).value).toBe('VPN Setup Guide')
    })

    // Modify title to make it dirty
    const titleInput = screen.getByLabelText('Title') as HTMLInputElement
    await user.clear(titleInput)
    await user.type(titleInput, 'VPN Setup Guide v2')

    // Click save
    const saveBtn = screen.getByText('Save Article')
    await user.click(saveBtn)

    await waitFor(() => {
      expect(managementApi.updateArticle).toHaveBeenCalled()
      expect(managementApi.createArticle).not.toHaveBeenCalled()
    })
  })

  it('shows error for non-manual articles', async () => {
    vi.mocked(managementApi.getArticle).mockResolvedValue({
      ...mockArticleDetail,
      source_type: 'pdf',
    })

    renderWithQuery(
      createElement(ArticleEditor, { onBack: vi.fn(), mode: 'edit', articleId: 'pdf1' }),
    )

    await waitFor(() => {
      expect(screen.getByText(/Only manual articles can be edited/)).toBeTruthy()
    })
  })

  it('renders create mode by default', () => {
    renderWithQuery(
      createElement(ArticleEditor, { onBack: vi.fn() }),
    )

    expect(screen.getByText('Create New Article')).toBeTruthy()
  })
})
