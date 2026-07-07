<script setup lang="ts">
// Un turno: header sticky (numero, orario, prompt, aggregati) + le righe
// (eventi, marker subagente, separatori temporali) nell'ordine cronologico
// già calcolato da TimelineView. Tipi duplicati qui (struttura compatibile
// con quelli di TimelineView.vue) per restare nel perimetro di file di
// competenza di questo agente.
import { formatDuration, formatTime, formatTokens } from '../../utils/format'
import type { EventSummary } from '../../types'
import ContextGauge from './ContextGauge.vue'
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
  | { rowKind: 'event'; event: EventSummary; nextRt?: EventSummary }
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

/**
 * Colore dell'indicatore sinistro (il "tacchino" sulla colonna di flusso)
 * per tipo di riga: round trip = accento, hook = grigio (verde per il prompt
 * utente che apre il giro), mcp = viola, subagente = arancio. Il gap non ha
 * indicatore.
 */
function rowAccent(row: TimelineRow): string {
  if (row.rowKind === 'gap') return 'transparent'
  if (row.rowKind === 'subagent') return '#f0883e'
  const e = row.event
  if (e.kind === 'round_trip') {
    return e.status != null && e.status !== 200 ? 'var(--danger)' : 'var(--accent)'
  }
  if (e.kind === 'mcp') return '#a78bfa'
  if (e.subkind === 'UserPromptSubmit') return 'var(--accent-live)'
  return 'var(--muted)'
}
</script>

<template>
  <section class="turn-group">
    <header class="turn-header" :style="{ top: `${stickyOffset}px` }">
      <div class="turn-title">
        <!-- turno 0 = eventi prima del primo prompt (SessionStart, traffico di
             servizio): non è un turno utente, quindi niente numerazione -->
        <span class="turn-badge">{{
          group.turnIndex === null ? 'avvio' : group.turnIndex === 0 ? 'pre-prompt' : `Turno ${group.turnIndex}`
        }}</span>
        <span class="turn-time">{{ formatTime(group.startTs) }}</span>
        <span class="turn-stats">
          {{ group.roundTrips }} round trip · {{ formatTokens(group.outputTokens) }} out ·
          {{ formatDuration(group.durationS) }}
        </span>
      </div>
      <p v-if="group.promptSnippet" class="turn-prompt">{{ group.promptSnippet }}</p>
    </header>

    <TransitionGroup name="row" tag="div" class="rows">
      <div
        v-for="(row, i) in group.rows"
        :key="rowKey(row, i)"
        class="row-wrap"
        :class="{ 'is-gap': row.rowKind === 'gap' }"
        :style="{ '--row-accent': rowAccent(row) }"
      >
        <div v-if="row.rowKind === 'gap'" class="gap-sep">··· {{ formatDuration(row.seconds) }} ···</div>
        <SubagentBlock v-else-if="row.rowKind === 'subagent'" :data="row.data" />
        <!-- round trip: card + gauge di riempimento contesto in una colonna
             dedicata a destra (stesso criterio non lineare della statusline) -->
        <div v-else-if="row.event.kind === 'round_trip'" class="rt-line">
          <EventCard :event="row.event" class="rt-card" />
          <ContextGauge :usage="row.event.usage" :model="row.event.model" class="rt-gauge" />
        </div>
        <McpCard v-else-if="row.event.kind === 'mcp'" :event="row.event" />
        <!-- hook: il tool_use mostra anche il contesto DOPO di sé, cioè
             l'input del round trip successivo (che porta il tool_result) -->
        <div v-else class="rt-line">
          <HookMarker :event="row.event" class="rt-card" />
          <ContextGauge
            v-if="row.event.subkind === 'PreToolUse' && row.nextRt"
            :usage="row.nextRt.usage"
            :model="row.nextRt.model"
            class="rt-gauge hook-gauge"
          />
        </div>
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
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 0.4rem 1.5rem 0.8rem;
  gap: 0.4rem;
}

/* colonna di flusso: linea verticale continua che collega le righe del turno */
.rows::before {
  content: '';
  position: absolute;
  left: 1.5rem;
  top: 0.4rem;
  bottom: 0.8rem;
  width: 2px;
  background-color: var(--border);
  border-radius: 2px;
}

.row-wrap {
  position: relative;
  display: flex;
  flex-direction: column;
  padding-left: 0.75rem;
  /* segmento colorato per tipo, sovrapposto alla colonna di flusso grigia:
     dove c'è una riga il flusso è colorato, nei gap resta grigio */
  border-left: 3px solid var(--row-accent, transparent);
}

.row-wrap.is-gap {
  border-left-color: transparent;
}

/* riga round trip: card + colonna gauge contesto allineata a destra */
.rt-line {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.rt-card {
  flex: 1;
  min-width: 0;
}

.rt-gauge {
  flex-shrink: 0;
  margin-top: 0.55rem;
}

/* sul marker tool_use (riga sottile) il gauge si allinea al testo */
.rt-gauge.hook-gauge {
  margin-top: 0.15rem;
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
