import { describe, it, expect, beforeEach } from 'vitest'
import { useSidebarStore } from '../../src/sidebar/store/sidebarStore'

describe('KB Context Picker — store actions', () => {
  beforeEach(() => {
    useSidebarStore.setState({ pinnedArticles: [] })
  })

  it('pinArticle adds an article to the store', () => {
    useSidebarStore.getState().pinArticle({ article_id: 'abc123', title: 'VPN Guide' })
    const pinned = useSidebarStore.getState().pinnedArticles
    expect(pinned).toHaveLength(1)
    expect(pinned[0]).toEqual({ article_id: 'abc123', title: 'VPN Guide' })
  })

  it('unpinArticle removes by ID', () => {
    useSidebarStore.getState().pinArticle({ article_id: 'abc123', title: 'VPN Guide' })
    useSidebarStore.getState().pinArticle({ article_id: 'def456', title: 'Printer Setup' })
    expect(useSidebarStore.getState().pinnedArticles).toHaveLength(2)

    useSidebarStore.getState().unpinArticle('abc123')
    const pinned = useSidebarStore.getState().pinnedArticles
    expect(pinned).toHaveLength(1)
    expect(pinned[0].article_id).toBe('def456')
  })

  it('duplicate pinArticle for same ID does not add twice', () => {
    useSidebarStore.getState().pinArticle({ article_id: 'abc123', title: 'VPN Guide' })
    useSidebarStore.getState().pinArticle({ article_id: 'abc123', title: 'VPN Guide' })
    expect(useSidebarStore.getState().pinnedArticles).toHaveLength(1)
  })

  it('pinArticle enforces max 10 articles', () => {
    for (let i = 0; i < 10; i++) {
      useSidebarStore.getState().pinArticle({ article_id: `art_${i}`, title: `Article ${i}` })
    }
    expect(useSidebarStore.getState().pinnedArticles).toHaveLength(10)

    // 11th pin should be rejected
    useSidebarStore.getState().pinArticle({ article_id: 'art_overflow', title: 'Overflow' })
    expect(useSidebarStore.getState().pinnedArticles).toHaveLength(10)
  })

  it('reset clears pinnedArticles', () => {
    useSidebarStore.getState().pinArticle({ article_id: 'abc123', title: 'VPN Guide' })
    useSidebarStore.getState().setReply('Some reply')
    useSidebarStore.getState().reset()

    expect(useSidebarStore.getState().reply).toBe('')
    expect(useSidebarStore.getState().pinnedArticles).toHaveLength(0)
  })
})
