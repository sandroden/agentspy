<script setup lang="ts">
// Card compatta per un evento MCP: subkind "<server>:<metodo>", durata
// request->response (già corretta lato backend: ts_start/ts_end di un evento
// mcp sono ts_request/ts_response, vedi ingest.py). Accento cromatico diverso
// da EventCard/HookMarker per distinguerla a colpo d'occhio.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatDuration, formatTime } from '../../utils/format'
import type { EventSummary } from '../../types'

const props = defineProps<{ event: EventSummary }>()

const spy = useSpyStore()

const selected = computed(() => spy.selectedEventId === props.event.id)

function onClick() {
  void spy.select(props.event.id)
}
</script>

<template>
  <article class="mcp-card" :class="{ selected }" :data-event-id="event.id" @click="onClick">
    <span class="tag">mcp</span>
    <span class="subkind">{{ event.subkind || '—' }}</span>
    <span class="time">{{ formatTime(event.ts_start) }}</span>
    <span class="duration">{{ formatDuration(event.duration_s) }}</span>
    <p v-if="event.snippet" class="snippet">{{ event.snippet }}</p>
  </article>
</template>

<style scoped>
.mcp-card {
  --mcp-accent: #2dd4bf;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  flex-wrap: wrap;
  padding: 0.4rem 0.7rem;
  background-color: var(--panel);
  border: 1px solid var(--mcp-accent);
  border-left-width: 3px;
  border-radius: 6px;
  font-size: 0.78rem;
  cursor: pointer;
}

.mcp-card:hover {
  filter: brightness(1.1);
}

.mcp-card.selected {
  box-shadow: 0 0 0 1px var(--mcp-accent);
}

.tag {
  color: var(--mcp-accent);
  font-weight: 700;
  font-size: 0.68rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.subkind {
  font-weight: 600;
  color: var(--text);
}

.time,
.duration {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.snippet {
  flex-basis: 100%;
  color: var(--text);
  opacity: 0.8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
