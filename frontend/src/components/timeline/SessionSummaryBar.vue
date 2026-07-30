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

// Le card leggono le stats per round trip (come la dashboard), tenute fresche
// dal composable condiviso con la barra del player.
const { session, stats } = useSessionStats()

/** prompt utente fino al punto del player (gli hook UserPromptSubmit sono già
 *  in events): in pausa deve contare come le altre card, non l'intera sessione. */
const promptCount = computed(
  () =>
    spy.visibleEvents.filter((e) => e.kind === 'hook' && e.subkind === 'UserPromptSubmit').length,
)

/** Posizione del player passata alle card: in LIVE nessun taglio (null), in
 *  pausa le metriche della sessione si fermano all'evento corrente. */
const cursorTs = computed(() => (spy.live ? null : (spy.cursorEvent?.ts_start ?? null)))
const cursorEventId = computed(() => (spy.live ? null : (spy.cursorEvent?.id ?? null)))
const cursorLabel = computed(() => {
  if (spy.live) return null
  const { index, total } = spy.playerPosition
  return total > 0 ? `evento ${index + 1}/${total}` : null
})

/** discendenti (ricorsivi) della sessione aperta. */
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
