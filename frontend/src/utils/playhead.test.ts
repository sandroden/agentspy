import { describe, it, expect } from 'vitest'
import { statsUpTo, statsForEvent } from './playhead'
import type { StatsItem } from '../types'

function rt(event_id: number, ts_start: number): StatsItem {
  return {
    event_id,
    turn_index: 1,
    ts_start,
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
  }
}

const STATS = [rt(1, 100), rt(2, 200), rt(3, 300)]

describe('statsUpTo', () => {
  it('keeps the round trips up to the cursor, inclusive', () => {
    expect(statsUpTo(STATS, 200).map((s) => s.event_id)).toEqual([1, 2])
  })

  it('null cursor means no cut (live mode)', () => {
    expect(statsUpTo(STATS, null)).toBe(STATS)
  })

  it('a cursor before the first round trip yields nothing', () => {
    expect(statsUpTo(STATS, 50)).toEqual([])
  })

  it('a cursor on a hook after the last round trip keeps them all', () => {
    expect(statsUpTo(STATS, 999)).toHaveLength(3)
  })
})

describe('statsForEvent', () => {
  it('finds the round trip the player sits on', () => {
    expect(statsForEvent(STATS, 2)?.ts_start).toBe(200)
  })

  it('returns null on a hook / MCP event, which has no usage of its own', () => {
    expect(statsForEvent(STATS, 42)).toBeNull()
    expect(statsForEvent(STATS, null)).toBeNull()
  })
})
