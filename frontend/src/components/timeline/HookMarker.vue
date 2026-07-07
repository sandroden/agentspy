<script setup lang="ts">
// Marker sottile per un evento hook: una riga, non una card. Per
// PreToolUse/PostToolUse mostra il nome del tool se il payload completo è già
// in cache (click precedente) — lo schema esatto del payload hook non è
// ancora verificato empiricamente (vedi correlate.py), quindi il campo è
// letto in modo difensivo e omesso se assente.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatTime } from '../../utils/format'
import type { EventSummary } from '../../types'

const props = defineProps<{ event: EventSummary }>()

const spy = useSpyStore()

const selected = computed(() => spy.selectedEventId === props.event.id)

const toolName = computed(() => {
  if (props.event.subkind !== 'PreToolUse' && props.event.subkind !== 'PostToolUse') return null
  const detail = spy.detailCache[props.event.id]
  const payload = detail?.payload as { tool_name?: unknown } | undefined
  return typeof payload?.tool_name === 'string' ? payload.tool_name : null
})

function onClick() {
  void spy.select(props.event.id)
}
</script>

<template>
  <div class="hook-marker" :class="{ selected }" :data-event-id="event.id" @click="onClick">
    <span class="icon">▸</span>
    <span class="subkind">{{ event.subkind || 'hook' }}</span>
    <span v-if="toolName" class="tool">{{ toolName }}</span>
    <span class="time">{{ formatTime(event.ts_start) }}</span>
  </div>
</template>

<style scoped>
.hook-marker {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.15rem 0.5rem;
  border-left: 2px solid transparent;
  color: var(--muted);
  font-size: 0.75rem;
  cursor: pointer;
}

.hook-marker:hover {
  color: var(--text);
}

.hook-marker.selected {
  border-left-color: var(--accent);
  color: var(--text);
}

.icon {
  color: var(--muted);
}

.subkind {
  font-weight: 600;
}

.tool {
  color: var(--accent-live);
}

.time {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}
</style>
