<script setup lang="ts">
// Compact card for an MCP event: subkind "<server>:<method>", request->response
// duration (already corrected server-side: an mcp event's ts_start/ts_end are
// ts_request/ts_response, see ingest.py). Its own accent color makes it
// recognizable at a glance among the round-trip swimlane rows.
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
    <span class="tag"><span class="mcp-icon">🔌</span>mcp</span>
    <span class="subkind">{{ event.subkind || '—' }}</span>
    <span class="time">{{ formatTime(event.ts_start) }}</span>
    <span class="duration">{{ formatDuration(event.duration_s) }}</span>
    <p v-if="event.snippet" class="snippet">{{ event.snippet }}</p>
  </article>
</template>

<style scoped>
.mcp-card {
  --mcp-accent: #a78bfa;
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
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  color: var(--mcp-accent);
  font-weight: 700;
  font-size: 0.68rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.mcp-icon {
  font-size: 0.8rem;
  line-height: 1;
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
