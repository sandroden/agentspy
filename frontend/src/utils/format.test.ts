import { describe, it, expect } from 'vitest'
import { formatTokens, formatDuration, formatTime } from './format'

describe('formatTokens', () => {
  it('keeps small counts as-is', () => {
    expect(formatTokens(0)).toBe('0')
    expect(formatTokens(999)).toBe('999')
  })

  it('abbreviates thousands and millions to one decimal', () => {
    expect(formatTokens(16_351)).toBe('16.4k')
    expect(formatTokens(1_000)).toBe('1.0k')
    expect(formatTokens(2_500_000)).toBe('2.5M')
  })

  it('treats null/undefined as zero and keeps the sign for negatives', () => {
    expect(formatTokens(null)).toBe('0')
    expect(formatTokens(undefined)).toBe('0')
    expect(formatTokens(-1500)).toBe('-1.5k')
  })
})

describe('formatDuration', () => {
  it('renders sub-second as milliseconds', () => {
    expect(formatDuration(0.25)).toBe('250ms')
  })

  it('renders seconds with two decimals under a minute', () => {
    expect(formatDuration(3.91)).toBe('3.91s')
  })

  it('renders minutes and zero-padded seconds past a minute', () => {
    expect(formatDuration(829)).toBe('13m 49s')
    expect(formatDuration(65)).toBe('1m 05s')
  })

  it('null → em dash', () => {
    expect(formatDuration(null)).toBe('—')
  })
})

describe('formatTime', () => {
  it('null → placeholder', () => {
    expect(formatTime(null)).toBe('--:--:--')
  })

  it('formats an epoch to a zero-padded HH:MM:SS', () => {
    expect(formatTime(1_783_440_726)).toMatch(/^\d{2}:\d{2}:\d{2}$/)
  })
})
