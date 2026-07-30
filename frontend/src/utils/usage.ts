/**
 * Token totals of a series of round trips.
 *
 * Extracted from MetricCards because the player bar shows the same numbers in
 * compact form: one definition of "context", "consumed" and aggregated usage,
 * so the sticky pill and the cards can never disagree.
 */
import type { StatsItem, Usage } from '../types'

/** Tokens "in context" for a round trip: new input + cache read + cache write. */
export function contextTokens(s: StatsItem): number {
  return s.input_tokens + s.cache_read_tokens + s.cache_write_tokens
}

/** Tokens consumed (contribution to the integral): context + output. */
export function consumedTokens(s: StatsItem): number {
  return contextTokens(s) + s.output_tokens
}

/** Sums the usage of a series of round trips, cache-write tiers included: they
 *  drive the cost (1h = 2×input, 5m = 1.25×), see utils/cache.ts. */
export function aggregateUsage(list: StatsItem[]): Usage {
  return list.reduce<Usage>(
    (acc, s) => ({
      input_tokens: acc.input_tokens + s.input_tokens,
      output_tokens: acc.output_tokens + s.output_tokens,
      cache_read_tokens: acc.cache_read_tokens + s.cache_read_tokens,
      cache_write_tokens: acc.cache_write_tokens + s.cache_write_tokens,
      // summed as 0 when the tier is unreported: the unknown share stays
      // visible as the residual (cache_write - 5m - 1h)
      cache_write_5m_tokens: (acc.cache_write_5m_tokens ?? 0) + (s.cache_write_5m_tokens ?? 0),
      cache_write_1h_tokens: (acc.cache_write_1h_tokens ?? 0) + (s.cache_write_1h_tokens ?? 0),
    }),
    {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
      cache_write_5m_tokens: 0,
      cache_write_1h_tokens: 0,
    }
  )
}

/** Total consumed tokens (the integral) of a series of round trips. */
export function totalConsumed(list: StatsItem[]): number {
  return list.reduce((sum, s) => sum + consumedTokens(s), 0)
}

/** Largest context seen across a series of round trips. */
export function peakContext(list: StatsItem[]): number {
  return list.length ? Math.max(...list.map(contextTokens)) : 0
}
