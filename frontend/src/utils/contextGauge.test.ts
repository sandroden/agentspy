import { describe, it, expect } from 'vitest'
import { contextSizeFor, contextGauge, BLOCKS_TOTAL } from './contextGauge'

describe('contextSizeFor', () => {
  it('current 1M families → 1M', () => {
    expect(contextSizeFor('claude-opus-4-8')).toBe(1_000_000)
    expect(contextSizeFor('claude-sonnet-5')).toBe(1_000_000)
    expect(contextSizeFor('claude-fable-5')).toBe(1_000_000)
    expect(contextSizeFor('claude-opus-4-5')).toBe(1_000_000)
    expect(contextSizeFor('claude-sonnet-4-5')).toBe(1_000_000)
  })

  it('Haiku (all generations) → 200k', () => {
    expect(contextSizeFor('claude-haiku-4-5')).toBe(200_000)
    expect(contextSizeFor('claude-3-5-haiku-20241022')).toBe(200_000)
  })

  it('the [1m] marker wins even over haiku', () => {
    expect(contextSizeFor('claude-haiku-4-5[1m]')).toBe(1_000_000)
    expect(contextSizeFor('claude-opus-4-8[1m]')).toBe(1_000_000)
  })

  it('Claude 1/2/3 families → 200k', () => {
    expect(contextSizeFor('claude-3-5-sonnet-20241022')).toBe(200_000)
    expect(contextSizeFor('claude-3-opus-20240229')).toBe(200_000)
    expect(contextSizeFor('claude-2.1')).toBe(200_000)
  })

  it('pre-4.5 Opus/Sonnet 4.x keep the classic 200k', () => {
    expect(contextSizeFor('claude-opus-4-1')).toBe(200_000)
    expect(contextSizeFor('claude-opus-4-20250514')).toBe(200_000)
    expect(contextSizeFor('claude-sonnet-4-20250514')).toBe(200_000)
  })

  it('the 4.5+ boundary flips Opus/Sonnet to 1M', () => {
    expect(contextSizeFor('claude-opus-4-1')).toBe(200_000)
    expect(contextSizeFor('claude-opus-4-5')).toBe(1_000_000)
    expect(contextSizeFor('claude-sonnet-4-1')).toBe(200_000)
    expect(contextSizeFor('claude-sonnet-4-5')).toBe(1_000_000)
  })

  it('null/undefined and unknown/future ids default to 1M', () => {
    expect(contextSizeFor(null)).toBe(1_000_000)
    expect(contextSizeFor(undefined)).toBe(1_000_000)
    expect(contextSizeFor('')).toBe(1_000_000)
    expect(contextSizeFor('claude-zzz-9')).toBe(1_000_000)
    expect(contextSizeFor('some-future-model')).toBe(1_000_000)
  })
})

describe('contextGauge', () => {
  it('uses the small-context profile [30,50,75] for 200k windows', () => {
    // pct=25 is below the first threshold (30) → green zone (index 0).
    const g = contextGauge(50_000, 200_000)
    expect(g.pct).toBe(25)
    expect(g.zone).toBe(0)
    expect(g.color).toBe('#3fb950')
  })

  it('uses the large-context profile [12,25,60] for 1M windows', () => {
    // 25% on a 1M window sits at the amber/yellow boundary (threshold[1]=25),
    // i.e. still zone 1 (amber) — a case the 200k profile would call green.
    const g = contextGauge(250_000, 1_000_000)
    expect(g.pct).toBe(25)
    expect(g.zone).toBe(1)
  })

  it('past every threshold → full bar, red zone', () => {
    const g = contextGauge(950_000, 1_000_000)
    expect(g.pct).toBe(95)
    expect(g.zone).toBe(3)
    expect(g.filled).toBe(BLOCKS_TOTAL)
    expect(g.color).toBe('#f85149')
  })

  it('empty context → zone 0, zero blocks filled', () => {
    const g = contextGauge(0, 1_000_000)
    expect(g.pct).toBe(0)
    expect(g.zone).toBe(0)
    expect(g.filled).toBe(0)
  })
})
