<script setup lang="ts">
// Marcatore discreto per un evento hook (SessionStart, Stop, PreCompact, ...):
// visibile solo con spy.showHooks attivo (toggle in TimeControls). Mostra che
// in quel punto della timeline Claude Code ha dato spazio a una reazione
// (es. un hook utente che blocca un comando); il click apre il payload nel
// DetailPanel, che sa già renderizzare kind='hook'.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatTime } from '../../utils/format'
import type { EventSummary } from '../../types'

const props = defineProps<{ event: EventSummary }>()
const spy = useSpyStore()

const selected = computed(() => spy.selectedEventId === props.event.id)

function onClick() {
  void spy.select(props.event.id)
}
</script>

<template>
  <div class="hook-row">
    <button class="hook-marker" :class="{ selected }" title="hook di Claude Code — click per il payload" @click="onClick">
      <span class="icon">⚓︎</span>
      <span class="name">{{ event.subkind }}</span>
      <span class="time">{{ formatTime(event.ts_start) }}</span>
    </button>
    <div class="hook-line" />
  </div>
</template>

<style scoped>
.hook-row {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 10px;
  align-items: center;
  margin: 2px 0;
}

.hook-marker {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  justify-self: start;
  background: none;
  color: var(--muted);
  border: 1px dashed var(--border);
  border-radius: 999px;
  padding: 0.1rem 0.5rem;
  font-size: 0.68rem;
  cursor: pointer;
  white-space: nowrap;
}

.hook-marker:hover {
  color: var(--text);
  border-color: var(--muted);
}

.hook-marker.selected {
  color: var(--text);
  border-style: solid;
  border-color: var(--accent, var(--muted));
}

.icon {
  font-size: 0.7rem;
  opacity: 0.8;
}

.time {
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}

.hook-line {
  border-top: 1px dashed var(--border);
  opacity: 0.5;
}
</style>
