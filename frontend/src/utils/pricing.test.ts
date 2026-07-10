import { describe, it, expect } from 'vitest'
import { pricingFor, estimateCost, formatCost } from './pricing'
import type { Usage } from '../types'

describe('pricingFor', () => {
  it('maps each family to its tier', () => {
    expect(pricingFor('claude-sonnet-5').input).toBe(3)
    expect(pricingFor('claude-haiku-4-5').input).toBe(1)
    expect(pricingFor('claude-opus-4-8').input).toBe(5)
  })

  it('unknown/fable fall back to the opus tier', () => {
    expect(pricingFor('gpt-4o')).toEqual(pricingFor('claude-opus-4-8'))
    expect(pricingFor('claude-fable-5').input).toBe(5)
  })
})

describe('estimateCost', () => {
  const usage: Usage = {
    input_tokens: 1000,
    output_tokens: 200,
    cache_read_tokens: 10_000,
    cache_write_tokens: 500,
  }

  it('sums the four buckets at the model tier (dollars)', () => {
    // opus: 1000*5 + 200*25 + 10000*0.5 + 500*6.25 = 18125 µ$ = $0.018125
    expect(estimateCost(usage, 'claude-opus-4-8')).toBeCloseTo(0.018125, 9)
  })

  it('scales down for the cheaper sonnet tier', () => {
    // sonnet: 1000*3 + 200*15 + 10000*0.3 + 500*3.75 = 10875 µ$
    expect(estimateCost(usage, 'claude-sonnet-5')).toBeCloseTo(0.010875, 9)
    expect(estimateCost(usage, 'claude-sonnet-5')).toBeLessThan(
      estimateCost(usage, 'claude-opus-4-8')
    )
  })

  it('zero usage costs nothing', () => {
    const empty: Usage = {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
    }
    expect(estimateCost(empty, 'claude-opus-4-8')).toBe(0)
  })
})

describe('formatCost', () => {
  it('picks precision by scale', () => {
    expect(formatCost(0)).toBe('$0')
    expect(formatCost(-1)).toBe('$0')
    expect(formatCost(0.0001234)).toBe('$0.0001')
    expect(formatCost(0.018125)).toBe('$0.018')
    expect(formatCost(12.345)).toBe('$12.35')
  })
})
