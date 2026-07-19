<script setup lang="ts">
// One turn: sticky header (number, time, prompt, aggregates) + its rows
// (round trips, sub-agent pointers, mcp calls, time-gap separators) in the
// chronological order already computed by TimelineView, rendered as a
// Trigger | Claude (LLM) | Tools swimlane.
import { computed } from 'vue'
import { formatDuration, formatTime, formatTokens } from '../../utils/format'
import type { EventSummary } from '../../types'
import HookMarker from './HookMarker.vue'
import McpCard from './McpCard.vue'
import RoundTripRow from './RoundTripRow.vue'
import SubagentBlock from './SubagentBlock.vue'

interface SubagentRowData {
  agentId: string
  childId: string | null
  ts: number
  label: string
}

type TimelineRow =
  | { rowKind: 'event'; event: EventSummary; nextRt?: EventSummary }
  | { rowKind: 'hook'; event: EventSummary }
  | { rowKind: 'subagent'; data: SubagentRowData }
  | { rowKind: 'gap'; seconds: number }

interface TimelineGroup {
  key: string
  turnIndex: number | null
  startTs: number | null
  promptSnippet: string
  rows: TimelineRow[]
  roundTrips: number
  outputTokens: number
  durationS: number | null
}

const props = defineProps<{
  group: TimelineGroup
  stickyOffset: number
}>()

function rowKey(row: TimelineRow, index: number): string {
  if (row.rowKind === 'event' || row.rowKind === 'hook') return `event-${row.event.id}`
  if (row.rowKind === 'subagent') return `subagent-${row.data.agentId}-${row.data.ts}`
  return `gap-${props.group.key}-${index}`
}

/** Sequential round-trip number (n/total) for the row-kind='event' rows only. */
const roundTripNumbers = computed<Map<number, number>>(() => {
  const m = new Map<number, number>()
  let n = 0
  for (const row of props.group.rows) {
    if (row.rowKind === 'event' && row.event.kind === 'round_trip') {
      n += 1
      m.set(row.event.id, n)
    }
  }
  return m
})

/** The first round-trip row gets the user bubble (the turn's prompt). */
const firstRoundTripId = computed<number | null>(() => {
  for (const row of props.group.rows) {
    if (row.rowKind === 'event' && row.event.kind === 'round_trip') return row.event.id
  }
  return null
})
</script>

<template>
  <section class="turn-group">
    <header class="turn-header" :style="{ top: `${stickyOffset}px` }">
      <div class="turn-title">
        <!-- turn 0 (or no turn at all) = events before the first prompt
             (SessionStart, service traffic): not a user turn, so no
             numbering — and no "pre-prompt" jargon either, it's just "start". -->
        <span class="turn-badge">{{
          group.turnIndex === null || group.turnIndex === 0 ? 'start' : `Turn ${group.turnIndex}`
        }}</span>
        <span class="turn-time">{{ formatTime(group.startTs) }}</span>
        <span class="turn-stats">
          {{ group.roundTrips }} round trips · {{ formatTokens(group.outputTokens) }} out ·
          {{ formatDuration(group.durationS) }}
        </span>
      </div>
    </header>

    <div class="lanehead">
      <span title="Ciò che innesca il turno: il tuo prompt, l'avvio di un subagente o una notifica asincrona. Nel payload API sono tutti messaggi role=user.">Trigger</span>
      <span>Claude (LLM)</span>
      <span>Tools</span>
    </div>

    <TransitionGroup name="row" tag="div" class="rows">
      <div v-for="(row, i) in group.rows" :key="rowKey(row, i)" class="row-wrap">
        <div v-if="row.rowKind === 'gap'" class="gap-sep">··· {{ formatDuration(row.seconds) }} ···</div>
        <SubagentBlock v-else-if="row.rowKind === 'subagent'" :data="row.data" />
        <HookMarker v-else-if="row.rowKind === 'hook'" :event="row.event" />
        <RoundTripRow
          v-else-if="row.event.kind === 'round_trip'"
          :event="row.event"
          :rt-index="roundTripNumbers.get(row.event.id) ?? 1"
          :rt-total="group.roundTrips"
          :user-text="row.event.id === firstRoundTripId ? group.promptSnippet : undefined"
        />
        <McpCard v-else-if="row.event.kind === 'mcp'" :event="row.event" class="mcp-row" />
      </div>
    </TransitionGroup>
  </section>
</template>

<style scoped>
.turn-group {
  display: flex;
  flex-direction: column;
}

.turn-header {
  position: sticky;
  z-index: 3;
  background-color: var(--bg);
  padding: 0.6rem 1.5rem 0.4rem;
  border-bottom: 1px solid var(--border);
}

.turn-title {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.turn-badge {
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--text);
}

.turn-time {
  color: var(--muted);
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
}

.turn-stats {
  margin-left: auto;
  color: var(--muted);
  font-size: 0.75rem;
}

.lanehead {
  display: grid;
  grid-template-columns: 130px 1fr 230px;
  gap: 10px;
  padding: 9px 1.5rem;
  background-color: var(--panel);
  border-bottom: 1px solid var(--border);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted-faint);
}

.rows {
  display: flex;
  flex-direction: column;
  padding: 0 1.5rem 0.8rem;
}

.mcp-row {
  margin: 6px 0;
}

.gap-sep {
  align-self: center;
  color: var(--muted);
  font-size: 0.7rem;
  letter-spacing: 0.03em;
  padding: 0.4rem 0;
  opacity: 0.7;
}

.row-enter-active,
.row-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.row-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}

.row-leave-to {
  opacity: 0;
}
</style>
