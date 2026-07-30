/**
 * Cache-write tiers (prompt-caching TTL).
 *
 * A cache write is billed by the TTL it was made with: 5 minutes (1.25×input)
 * or 1 hour (2×input). Claude Code picks the TTL per request, so a session
 * usually mixes the two — showing them merged hides both the strategy and the
 * real cost. The API reports the split in `usage.cache_creation`; the server
 * promotes it to the `cache_write_5m_tokens` / `cache_write_1h_tokens` columns,
 * left null by providers that don't report the tier.
 */

/** Minimal shape needed to split cache writes (Usage and StatsItem both match). */
export interface CacheWriteSource {
  cache_write_tokens: number
  cache_write_5m_tokens: number | null
  cache_write_1h_tokens: number | null
}

export interface CacheWriteTiers {
  /** tokens written with the 5-minute TTL. */
  m5: number
  /** tokens written with the 1-hour TTL. */
  h1: number
  /** tokens whose TTL the provider didn't report (never folded into a tier). */
  unknown: number
}

export function cacheWriteTiers(source: CacheWriteSource): CacheWriteTiers {
  const m5 = source.cache_write_5m_tokens ?? 0
  const h1 = source.cache_write_1h_tokens ?? 0
  return { m5, h1, unknown: Math.max(0, (source.cache_write_tokens ?? 0) - m5 - h1) }
}

/** Sums the tiers of several round trips / sessions (dashboard aggregates). */
export function sumCacheWriteTiers(sources: CacheWriteSource[]): CacheWriteTiers {
  return sources.reduce(
    (acc, s) => {
      const t = cacheWriteTiers(s)
      return { m5: acc.m5 + t.m5, h1: acc.h1 + t.h1, unknown: acc.unknown + t.unknown }
    },
    { m5: 0, h1: 0, unknown: 0 }
  )
}
