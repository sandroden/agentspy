import { describe, it, expect } from 'vitest'
import { cacheWriteTiers, sumCacheWriteTiers } from './cache'

describe('cacheWriteTiers', () => {
  it('splits the write between the two TTLs', () => {
    expect(
      cacheWriteTiers({
        cache_write_tokens: 8415,
        cache_write_5m_tokens: 0,
        cache_write_1h_tokens: 8415,
      })
    ).toEqual({ m5: 0, h1: 8415, unknown: 0 })
  })

  it('keeps an unreported TTL as unknown instead of folding it into 5m', () => {
    expect(
      cacheWriteTiers({
        cache_write_tokens: 120,
        cache_write_5m_tokens: null,
        cache_write_1h_tokens: null,
      })
    ).toEqual({ m5: 0, h1: 0, unknown: 120 })
  })

  it('never returns a negative residual', () => {
    // difesa: il totale della colonna non deve mai stare sotto la somma dei tier
    expect(
      cacheWriteTiers({
        cache_write_tokens: 10,
        cache_write_5m_tokens: 40,
        cache_write_1h_tokens: 0,
      }).unknown
    ).toBe(0)
  })

  it('sums the tiers of several round trips', () => {
    expect(
      sumCacheWriteTiers([
        { cache_write_tokens: 100, cache_write_5m_tokens: 100, cache_write_1h_tokens: 0 },
        { cache_write_tokens: 300, cache_write_5m_tokens: 0, cache_write_1h_tokens: 300 },
        { cache_write_tokens: 50, cache_write_5m_tokens: null, cache_write_1h_tokens: null },
      ])
    ).toEqual({ m5: 100, h1: 300, unknown: 50 })
  })
})
