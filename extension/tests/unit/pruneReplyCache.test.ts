import { describe, it, expect, vi } from 'vitest'
import { pruneReplyCache, REPLY_CACHE_MAX_ENTRIES, REPLY_CACHE_TTL_MS } from '../../src/sidebar/store/sidebarStore'

describe('pruneReplyCache', () => {
  it('filters expired entries', () => {
    const now = Date.now()
    vi.setSystemTime(now)
    const cache = {
      'ticket-1': { reply: 'old', timestamp: now - REPLY_CACHE_TTL_MS - 1 },
      'ticket-2': { reply: 'fresh', timestamp: now - 1000 },
    }
    const result = pruneReplyCache(cache)
    expect(Object.keys(result)).toEqual(['ticket-2'])
    expect(result['ticket-2'].reply).toBe('fresh')
    vi.useRealTimers()
  })

  it('keeps valid entries', () => {
    const now = Date.now()
    vi.setSystemTime(now)
    const cache = {
      'ticket-1': { reply: 'a', timestamp: now - 100 },
      'ticket-2': { reply: 'b', timestamp: now - 200 },
      'ticket-3': { reply: 'c', timestamp: now - 300 },
    }
    const result = pruneReplyCache(cache)
    expect(Object.keys(result)).toHaveLength(3)
    expect(result['ticket-1'].reply).toBe('a')
    expect(result['ticket-2'].reply).toBe('b')
    expect(result['ticket-3'].reply).toBe('c')
    vi.useRealTimers()
  })

  it('truncates to MAX_ENTRIES sorted by newest first', () => {
    const now = Date.now()
    vi.setSystemTime(now)
    const cache: Record<string, { reply: string; timestamp: number }> = {}
    for (let i = 0; i < REPLY_CACHE_MAX_ENTRIES + 5; i++) {
      cache[`ticket-${i}`] = { reply: `reply-${i}`, timestamp: now - i * 1000 }
    }
    const result = pruneReplyCache(cache)
    expect(Object.keys(result)).toHaveLength(REPLY_CACHE_MAX_ENTRIES)
    // Newest entry (ticket-0) should be present
    expect(result['ticket-0']).toBeDefined()
    // Oldest entries beyond the limit should be gone
    expect(result[`ticket-${REPLY_CACHE_MAX_ENTRIES + 4}`]).toBeUndefined()
    expect(result[`ticket-${REPLY_CACHE_MAX_ENTRIES + 3}`]).toBeUndefined()
    vi.useRealTimers()
  })

  it('handles empty cache', () => {
    const result = pruneReplyCache({})
    expect(result).toEqual({})
  })

  it('handles cache with exactly MAX_ENTRIES', () => {
    const now = Date.now()
    vi.setSystemTime(now)
    const cache: Record<string, { reply: string; timestamp: number }> = {}
    for (let i = 0; i < REPLY_CACHE_MAX_ENTRIES; i++) {
      cache[`ticket-${i}`] = { reply: `reply-${i}`, timestamp: now - i * 1000 }
    }
    const result = pruneReplyCache(cache)
    expect(Object.keys(result)).toHaveLength(REPLY_CACHE_MAX_ENTRIES)
    vi.useRealTimers()
  })
})
