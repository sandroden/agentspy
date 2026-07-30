import { describe, it, expect } from 'vitest'
import { aggregateUsage, consumedTokens, contextTokens, peakContext, totalConsumed } from './usage'
import type { StatsItem } from '../types'

function rt(partial: Partial<StatsItem>): StatsItem {
  return {
    event_id: 1,
    turn_index: 1,
    ts_start: 0,
    ttfb_s: null,
    duration_s: null,
    model: 'claude-opus-4-8',
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    cache_write_5m_tokens: null,
    cache_write_1h_tokens: null,
    system_chars: null,
    tools_chars: null,
    messages_chars: null,
    ...partial,
  }
}

const A = rt({ event_id: 1, input_tokens: 100, output_tokens: 50, cache_read_tokens: 1000, cache_write_tokens: 200, cache_write_1h_tokens: 200, cache_write_5m_tokens: 0 })
const B = rt({ event_id: 2, input_tokens: 10, output_tokens: 500, cache_read_tokens: 3000, cache_write_tokens: 40, cache_write_5m_tokens: 40, cache_write_1h_tokens: 0 })

describe('token totals', () => {
  it('context = new input + cache read + cache write, consumed adds the output', () => {
    expect(contextTokens(A)).toBe(1300)
    expect(consumedTokens(A)).toBe(1350)
  })

  it('the integral sums the round trips', () => {
    expect(totalConsumed([A, B])).toBe(1350 + 3550)
  })

  it('the peak is the largest context, not the last one', () => {
    expect(peakContext([B, A])).toBe(3050)
    expect(peakContext([])).toBe(0)
  })

  it('aggregate keeps the cache-write tiers, which drive the cost', () => {
    const u = aggregateUsage([A, B])
    expect(u.cache_write_tokens).toBe(240)
    expect(u.cache_write_1h_tokens).toBe(200)
    expect(u.cache_write_5m_tokens).toBe(40)
  })

  it('an unreported tier does not become 5m: it stays the residual', () => {
    const u = aggregateUsage([rt({ cache_write_tokens: 120 })])
    expect(u.cache_write_5m_tokens).toBe(0)
    expect(u.cache_write_1h_tokens).toBe(0)
    expect(u.cache_write_tokens).toBe(120)
  })
})
