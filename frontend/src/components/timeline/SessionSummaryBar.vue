<script setup lang="ts">
// Shown in place of the Glossary once its tips are dismissed: the session
// "numbers" — the same MetricCards used by the dashboard (peak context,
// consumed tokens, estimated cost, sub-agents…) — plus a "?" button to bring
// the tips back.
import { computed } from 'vue'
import { useSessionStats } from '../../composables/useSessionStats'
import { useSpyStore } from '../../stores/spy'
import type { Session } from '../../types'
import MetricCards from '../MetricCards.vue'

const emit = defineEmits<{ (e: 'show-tips'): void }>()

const spy = useSpyStore()

// The cards read the per-round-trip stats (like the dashboard), kept fresh by
// the composable shared with the player bar.
const { session, stats } = useSessionStats()

/** user prompts up to the player position (the UserPromptSubmit hooks are
 *  already in events): when paused it must count like the other cards, not the
 *  whole session. */
const promptCount = computed(
  () =>
    spy.visibleEvents.filter((e) => e.kind === 'hook' && e.subkind === 'UserPromptSubmit').length,
)

/** Player position passed to the cards: in LIVE no cut-off (null), when paused
 *  the session metrics stop at the current event. */
const cursorTs = computed(() => (spy.live ? null : (spy.cursorEvent?.ts_start ?? null)))
const cursorEventId = computed(() => (spy.live ? null : (spy.cursorEvent?.id ?? null)))
const cursorLabel = computed(() => {
  if (spy.live) return null
  const { index, total } = spy.playerPosition
  return total > 0 ? `event ${index + 1}/${total}` : null
})

/** (recursive) descendants of the open session. */
const subagents = computed<Session[]>(() => {
  const rootId = session.value?.id
  if (!rootId) return []
  const all = Object.values(spy.sessions)
  const out: Session[] = []
  const walk = (pid: string) => {
    for (const s of all) {
      if (s.parent_session_id === pid) {
        out.push(s)
        walk(s.id)
      }
    }
  }
  walk(rootId)
  return out
})
</script>

<template>
  <div v-if="session" class="summary-bar">
    <MetricCards
      :stats="stats"
      :model="session.model"
      :prompt-count="promptCount"
      :subagents="subagents"
      :cursor-ts="cursorTs"
      :cursor-event-id="cursorEventId"
      :cursor-label="cursorLabel"
    />
    <button class="show-btn" title="Show the explanations" @click="emit('show-tips')">?</button>
  </div>
</template>

<style scoped>
.summary-bar {
  display: flex;
  align-items: flex-start;
  gap: 1.1rem;
  border-bottom: 1px solid var(--border);
  background-color: var(--panel-alt);
  padding: 0.55rem 1.25rem;
}

.summary-bar > :first-child {
  flex: 1;
  min-width: 0;
}

.show-btn {
  margin-left: auto;
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background-color: var(--panel);
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 700;
  cursor: pointer;
}

.show-btn:hover {
  color: var(--text);
  border-color: var(--muted);
}
</style>
