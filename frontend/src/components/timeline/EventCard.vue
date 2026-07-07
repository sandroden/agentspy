<script setup lang="ts">
// Card di un round trip: modello, timing, mini-barra usage, stop_reason,
// badge tool, indicatore thinking (best-effort, solo se il payload è già in
// cache da un click precedente), snippet risposta. Bordo rosso se status != 200.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatDuration, formatTime } from '../../utils/format'
import type { EventSummary } from '../../types'
import UsageBar from './UsageBar.vue'

const props = defineProps<{ event: EventSummary }>()

const spy = useSpyStore()

const selected = computed(() => spy.selectedEventId === props.event.id)
const isError = computed(() => props.event.status != null && props.event.status !== 200)

/** claude-sonnet-4-5-20250929 -> sonnet-4.5 (stesso criterio di SessionsSidebar). */
function abbreviateModel(model: string | null): string {
  if (!model) return '—'
  const m = model.match(/claude-([a-z]+)-(\d+)(?:-(\d+))?/)
  if (m) {
    const [, family, major, minor] = m
    return minor ? `${family}-${major}.${minor}` : `${family}-${major}`
  }
  return model.length > 16 ? `${model.slice(0, 16)}…` : model
}

/** Best-effort: solo se il dettaglio completo è già in cache (click precedente). */
const hasThinking = computed(() => {
  const detail = spy.detailCache[props.event.id]
  const payload = detail?.payload as { response?: { message?: { content?: unknown[] } } } | undefined
  const content = payload?.response?.message?.content
  if (!Array.isArray(content)) return false
  return content.some(
    (block) => block && typeof block === 'object' && 'type' in block && (block as { type: string }).type === 'thinking'
  )
})

function onClick() {
  void spy.select(props.event.id)
}
</script>

<template>
  <article
    class="event-card"
    :class="{ selected, error: isError }"
    :data-event-id="event.id"
    @click="onClick"
  >
    <div class="row-top">
      <span class="chip model">{{ abbreviateModel(event.model) }}</span>
      <span class="time">{{ formatTime(event.ts_start) }}</span>
      <span class="timing">{{ formatDuration(event.duration_s) }}<template v-if="event.ttfb_s != null"> · ttfb {{ formatDuration(event.ttfb_s) }}</template></span>
      <span v-if="isError" class="status-badge">status {{ event.status }}</span>
      <span v-if="event.stop_reason" class="stop-reason">{{ event.stop_reason }}</span>
      <span v-if="hasThinking" class="thinking" title="il payload contiene un blocco 'thinking'">🧠 thinking</span>
    </div>

    <UsageBar class="usage" :usage="event.usage" />

    <div v-if="event.tool_names.length" class="tools">
      <span v-for="tool in event.tool_names" :key="tool" class="chip tool">{{ tool }}</span>
    </div>

    <p v-if="event.snippet" class="snippet">{{ event.snippet }}</p>
  </article>
</template>

<style scoped>
.event-card {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.55rem 0.75rem;
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
}

.event-card:hover {
  border-color: var(--accent);
}

.event-card.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.event-card.error {
  border-color: var(--danger);
}

.event-card.error.selected {
  box-shadow: 0 0 0 1px var(--danger);
}

.row-top {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: 0.78rem;
}

.chip {
  padding: 0.05rem 0.4rem;
  border-radius: 3px;
  background-color: var(--panel-alt);
  font-size: 0.72rem;
}

.chip.model {
  color: var(--accent);
  font-weight: 600;
}

.time,
.timing {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.status-badge {
  color: #fff;
  background-color: var(--danger);
  padding: 0.05rem 0.4rem;
  border-radius: 3px;
  font-weight: 600;
}

.stop-reason {
  color: var(--muted);
  font-style: italic;
}

.thinking {
  color: var(--muted);
}

.usage {
  max-width: 260px;
}

.tools {
  display: flex;
  gap: 0.3rem;
  flex-wrap: wrap;
}

.chip.tool {
  color: var(--accent-live);
}

.snippet {
  color: var(--text);
  font-size: 0.8rem;
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
