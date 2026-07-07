<script setup lang="ts">
// Un turno: header sticky (numero, orario, prompt, aggregati) + le righe
// (eventi, marker subagente, separatori temporali) nell'ordine cronologico
// già calcolato da TimelineView. Tipi duplicati qui (struttura compatibile
// con quelli di TimelineView.vue) per restare nel perimetro di file di
// competenza di questo agente.
import { formatDuration, formatTime, formatTokens } from '../../utils/format'
import type { EventSummary } from '../../types'
import EventCard from './EventCard.vue'
import HookMarker from './HookMarker.vue'
import McpCard from './McpCard.vue'
import SubagentBlock from './SubagentBlock.vue'

interface SubagentRowData {
  agentId: string
  childId: string | null
  ts: number
  label: string
}

type TimelineRow =
  | { rowKind: 'event'; event: EventSummary }
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
  if (row.rowKind === 'event') return `event-${row.event.id}`
  if (row.rowKind === 'subagent') return `subagent-${row.data.agentId}-${row.data.ts}`
  return `gap-${props.group.key}-${index}`
}
</script>

<template>
  <section class="turn-group">
    <header class="turn-header" :style="{ top: `${stickyOffset}px` }">
      <div class="turn-title">
        <span class="turn-badge">{{ group.turnIndex === null ? 'avvio' : `Turno ${group.turnIndex}` }}</span>
        <span class="turn-time">{{ formatTime(group.startTs) }}</span>
        <span class="turn-stats">
          {{ group.roundTrips }} round trip · {{ formatTokens(group.outputTokens) }} out ·
          {{ formatDuration(group.durationS) }}
        </span>
      </div>
      <p v-if="group.promptSnippet" class="turn-prompt">{{ group.promptSnippet }}</p>
    </header>

    <TransitionGroup name="row" tag="div" class="rows">
      <div v-for="(row, i) in group.rows" :key="rowKey(row, i)" class="row-wrap">
        <div v-if="row.rowKind === 'gap'" class="gap-sep">··· {{ formatDuration(row.seconds) }} ···</div>
        <SubagentBlock v-else-if="row.rowKind === 'subagent'" :data="row.data" />
        <EventCard v-else-if="row.event.kind === 'round_trip'" :event="row.event" />
        <McpCard v-else-if="row.event.kind === 'mcp'" :event="row.event" />
        <HookMarker v-else :event="row.event" />
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

.turn-prompt {
  margin-top: 0.25rem;
  color: var(--text);
  font-size: 0.82rem;
  font-style: italic;
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rows {
  display: flex;
  flex-direction: column;
  padding: 0.4rem 1.5rem 0.8rem;
  gap: 0.4rem;
}

.row-wrap {
  display: flex;
  flex-direction: column;
}

.gap-sep {
  align-self: center;
  color: var(--muted);
  font-size: 0.7rem;
  letter-spacing: 0.03em;
  padding: 0.15rem 0;
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
