/**
 * Stima del costo API a partire dai token reali.
 *
 * I prezzi sono espressi in micro-dollari per token (µ$/token), cioè
 * dollari per milione di token: 5 µ$/token = 5 $/Mtoken. Valori didattici
 * per confrontare l'impatto delle strategie, non un tariffario ufficiale.
 */
import type { Usage } from '../types'
import { modelFamily } from './model'

export interface Pricing {
  /** µ$/token per input nuovo. */
  input: number
  /** µ$/token per output generato. */
  output: number
  /** µ$/token per lettura dalla cache (parte fredda). */
  cache_read: number
  /** µ$/token per scrittura in cache. */
  cache_write: number
}

const PRICING: Record<string, Pricing> = {
  // Opus: base di riferimento.
  opus: { input: 5, output: 25, cache_read: 0.5, cache_write: 6.25 },
  // Sonnet: cache_read = 0.1×input, cache_write = 1.25×input.
  sonnet: { input: 3, output: 15, cache_read: 0.3, cache_write: 3.75 },
  // Haiku: cache_read = 0.1×input, cache_write = 1.25×input.
  haiku: { input: 1, output: 5, cache_read: 0.1, cache_write: 1.25 },
  // Fable: tariffario non pubblicato qui; usiamo la fascia Opus come stima.
  fable: { input: 5, output: 25, cache_read: 0.5, cache_write: 6.25 },
}

const DEFAULT_PRICING: Pricing = PRICING.opus

export function pricingFor(model: string | null | undefined): Pricing {
  return PRICING[modelFamily(model)] ?? DEFAULT_PRICING
}

/** Costo stimato in dollari per un dato Usage e modello. */
export function estimateCost(usage: Usage, model: string | null | undefined): number {
  const p = pricingFor(model)
  const microDollars =
    usage.input_tokens * p.input +
    usage.output_tokens * p.output +
    usage.cache_read_tokens * p.cache_read +
    usage.cache_write_tokens * p.cache_write
  return microDollars / 1_000_000
}

/** Formatta un costo in dollari con precisione adeguata alla scala. */
export function formatCost(dollars: number): string {
  if (dollars <= 0) return '$0'
  if (dollars < 0.01) return `$${dollars.toFixed(4)}`
  if (dollars < 1) return `$${dollars.toFixed(3)}`
  return `$${dollars.toFixed(2)}`
}
