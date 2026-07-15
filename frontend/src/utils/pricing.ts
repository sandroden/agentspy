/**
 * API cost estimate from actual tokens.
 *
 * Prices are expressed in micro-dollars per token (µ$/token), i.e.
 * dollars per million tokens: 5 µ$/token = $5/Mtoken. Didactic values
 * to compare the impact of strategies, not an official price list.
 */
import type { Usage } from '../types'
import { modelFamily } from './model'

export interface Pricing {
  /** µ$/token for new input. */
  input: number
  /** µ$/token for generated output. */
  output: number
  /** µ$/token for cache reads (cold part). */
  cache_read: number
  /** µ$/token for cache writes. */
  cache_write: number
}

const PRICING: Record<string, Pricing> = {
  // Opus: reference baseline.
  opus: { input: 5, output: 25, cache_read: 0.5, cache_write: 6.25 },
  // Sonnet: cache_read = 0.1×input, cache_write = 1.25×input.
  sonnet: { input: 3, output: 15, cache_read: 0.3, cache_write: 3.75 },
  // Haiku: cache_read = 0.1×input, cache_write = 1.25×input.
  haiku: { input: 1, output: 5, cache_read: 0.1, cache_write: 1.25 },
  // Fable: pricing not published here; we use the Opus tier as an estimate.
  fable: { input: 5, output: 25, cache_read: 0.5, cache_write: 6.25 },
  // GLM via OpenRouter (z-ai/glm-5.2, 2026-07): input $0.97/M, output $3.06/M,
  // cache read $0.18/M; cache writes are not billed separately there, so we
  // charge them as plain input. NB family-level like the others: the cheaper
  // variants (glm-4.7-flash ≈ input $0.06/M) are overestimated here.
  glm: { input: 0.97, output: 3.06, cache_read: 0.18, cache_write: 0.97 },
}

const DEFAULT_PRICING: Pricing = PRICING.opus

export function pricingFor(model: string | null | undefined): Pricing {
  return PRICING[modelFamily(model)] ?? DEFAULT_PRICING
}

/**
 * Estimated cost in dollars for a given Usage and model.
 *
 * NB: the token columns carry *context occupancy* (the prompt as seen at
 * message_start), which is what the gauge and the fill charts need. On turns
 * with extended thinking the API bills a larger cache-read *throughput* (the
 * prompt re-read across passes, reported in message_delta); on those rare turns
 * the cost here is therefore approximated on the prompt size, slightly below the
 * billed figure. A deliberate trade-off for a didactic tool — see the
 * _PROMPT_USAGE_KEYS note in server/agentspy_server/proxy.py.
 */
export function estimateCost(usage: Usage, model: string | null | undefined): number {
  const p = pricingFor(model)
  const microDollars =
    usage.input_tokens * p.input +
    usage.output_tokens * p.output +
    usage.cache_read_tokens * p.cache_read +
    usage.cache_write_tokens * p.cache_write
  return microDollars / 1_000_000
}

/** Formats a cost in dollars with precision suited to its scale. */
export function formatCost(dollars: number): string {
  if (dollars <= 0) return '$0'
  if (dollars < 0.01) return `$${dollars.toFixed(4)}`
  if (dollars < 1) return `$${dollars.toFixed(3)}`
  return `$${dollars.toFixed(2)}`
}
