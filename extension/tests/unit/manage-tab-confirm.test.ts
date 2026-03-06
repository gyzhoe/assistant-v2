import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act } from 'react'

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

vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))
Element.prototype.scrollIntoView = vi.fn()

const mockClearCollection = vi.fn().mockResolvedValue(undefined)

vi.mock('../../src/lib/api-client', () => ({
  apiClient: {
    clearCollection: (...args: unknown[]) => mockClearCollection(...args),
    health: vi.fn().mockResolvedValue({
      status: 'ok',
      llm_reachable: true,
      chroma_doc_counts: { whd_tickets: 10, kb_articles: 5 },
      version: '1.0.0',
    }),
  },
}))

describe('ManageTab — confirm dialog', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  async function renderManageTab(docCounts: Record<string, number> = { whd_tickets: 10, kb_articles: 5 }) {
    const React = await import('react')
    const { render, screen, fireEvent } = await import('@testing-library/react')
    const { ManageTab } = await import('../../src/sidebar/components/ManageTab')

    const onRefresh = vi.fn()
    const result = render(
      React.createElement(ManageTab, { docCounts, onRefresh }),
    )
    return { ...result, screen, fireEvent, onRefresh }
  }

  it('shows a Clear button for each non-empty collection', async () => {
    const { screen } = await renderManageTab()
    const clearButtons = screen.getAllByRole('button', { name: /clear/i })
    expect(clearButtons).toHaveLength(2)
  })

  it('opens a modal confirm dialog when Clear is clicked', async () => {
    const { screen, fireEvent } = await renderManageTab()
    const clearButtons = screen.getAllByRole('button', { name: /clear/i })

    await act(async () => {
      fireEvent.click(clearButtons[0])
    })

    // Radix AlertDialog renders a dialog with role="alertdialog"
    expect(screen.getByRole('alertdialog')).toBeTruthy()
    expect(screen.getByText(/permanently delete all documents/i)).toBeTruthy()
  })

  it('dialog shows the collection name in the description', async () => {
    const { screen, fireEvent } = await renderManageTab()
    const clearButtons = screen.getAllByRole('button', { name: /clear/i })

    await act(async () => {
      fireEvent.click(clearButtons[0]) // First collection is "Tickets"
    })

    // The description inside the dialog mentions the collection name
    expect(screen.getByText(/permanently delete all documents in the Tickets collection/i)).toBeTruthy()
  })

  it('Cancel button closes the dialog without clearing', async () => {
    const { screen, fireEvent } = await renderManageTab()
    const clearButtons = screen.getAllByRole('button', { name: /clear/i })

    await act(async () => {
      fireEvent.click(clearButtons[0])
    })

    const cancelBtn = screen.getByRole('button', { name: /cancel/i })
    await act(async () => {
      fireEvent.click(cancelBtn)
    })

    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(mockClearCollection).not.toHaveBeenCalled()
  })

  it('confirm button calls clearCollection and closes the dialog', async () => {
    const { screen, fireEvent, onRefresh } = await renderManageTab()
    const clearButtons = screen.getAllByRole('button', { name: /clear/i })

    await act(async () => {
      fireEvent.click(clearButtons[0])
    })

    const confirmBtn = screen.getByRole('button', { name: /yes, clear all/i })
    await act(async () => {
      fireEvent.click(confirmBtn)
    })

    expect(mockClearCollection).toHaveBeenCalledWith('whd_tickets')
    expect(onRefresh).toHaveBeenCalled()
  })
})
