/**
 * Playhead: reading the numbers "up to where the player is".
 *
 * When the timeline is paused on an event, the metrics next to it (tokens,
 * cost, peak context) must describe the session *up to that point*, not its
 * final total — otherwise stepping through the conversation tells you nothing
 * about how the spend built up. The cut is by timestamp, not by index: `stats`
 * only holds round trips while the player also steps over hooks and MCP calls,
 * so the two index spaces don't line up.
 */
import type { StatsItem } from '../types'

/** Round trips started no later than the cursor. `cursorTs` null = no cut. */
export function statsUpTo(stats: StatsItem[], cursorTs: number | null): StatsItem[] {
  if (cursorTs == null) return stats
  return stats.filter((s) => s.ts_start != null && s.ts_start <= cursorTs)
}

/** The round trip the player sits on, or null when the cursor is on a hook /
 *  MCP event (those have no usage of their own). */
export function statsForEvent(stats: StatsItem[], eventId: number | null): StatsItem | null {
  if (eventId == null) return null
  return stats.find((s) => s.event_id === eventId) ?? null
}
