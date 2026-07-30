/**
 * Per-round-trip stats of the open session, kept fresh.
 *
 * `spy.stats` is only filled when the session is opened, so on a live session
 * it goes stale as new round trips arrive; `statsBySession` is the cache the
 * dashboard uses and can be reloaded. Both the summary bar and the player's
 * compact readout need the same up-to-date series, hence one composable
 * instead of two copies of the watch.
 */
import { computed, watch } from 'vue'
import type { ComputedRef } from 'vue'
import { useSpyStore } from '../stores/spy'
import type { Session, StatsItem } from '../types'

export function useSessionStats(): {
  session: ComputedRef<Session | null>
  stats: ComputedRef<StatsItem[]>
} {
  const spy = useSpyStore()
  const session = computed<Session | null>(() => spy.currentSession)

  watch(
    () => (session.value ? `${session.value.id}:${session.value.round_trips}` : null),
    () => {
      if (session.value) void spy.loadStatsFor(session.value.id, true)
    },
    { immediate: true }
  )

  const stats = computed<StatsItem[]>(() =>
    session.value ? (spy.statsBySession[session.value.id] ?? spy.stats) : []
  )

  return { session, stats }
}
