import { describe, it, expect, vi, beforeEach, afterAll } from 'vitest'

// --- Mock chrome APIs ---
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k: string, cb: (r: Record<string, unknown>) => void) => cb({})) },
  },
})

describe('isCorsProbablyBlocked', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.resetModules()
  })

  afterAll(() => {
    globalThis.fetch = originalFetch
  })

  it('returns true when no-cors fetch gets opaque response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ type: 'opaque' })
    const { isCorsProbablyBlocked } = await import('../../src/lib/cors-detect')
    const result = await isCorsProbablyBlocked()
    expect(result).toBe(true)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/health'),
      expect.objectContaining({ mode: 'no-cors' }),
    )
  })

  it('returns false when no-cors fetch throws (server down)', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    const { isCorsProbablyBlocked } = await import('../../src/lib/cors-detect')
    const result = await isCorsProbablyBlocked()
    expect(result).toBe(false)
  })

  it('returns false when response type is basic (not CORS issue)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ type: 'basic' })
    const { isCorsProbablyBlocked } = await import('../../src/lib/cors-detect')
    const result = await isCorsProbablyBlocked()
    expect(result).toBe(false)
  })
})
