<script setup lang="ts">
// Marker sottile per un evento hook: una riga, non una card. Glifo e colore
// dipendono dal subkind (UserPromptSubmit apre un giro ed è il più marcato).
// Per PreToolUse/PostToolUse mostra il nome del tool se il payload completo è
// già in cache (click precedente) — lo schema esatto del payload hook non è
// ancora verificato empiricamente (vedi correlate.py), quindi il campo è
// letto in modo difensivo e omesso se assente.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatTime } from '../../utils/format'
import { toolIcon } from '../../utils/toolIcon'
import type { EventSummary } from '../../types'

const props = defineProps<{ event: EventSummary }>()

const spy = useSpyStore()

const selected = computed(() => spy.selectedEventId === props.event.id)

const isPrompt = computed(() => props.event.subkind === 'UserPromptSubmit')

/** Glifo per subkind: prompt utente ▶, tool 🔧, subagente 🤖, stop ■, altro ○. */
const glyph = computed(() => {
  switch (props.event.subkind) {
    case 'UserPromptSubmit':
      return '▶'
    case 'PreToolUse':
    case 'PostToolUse':
      return '🔧'
    case 'SubagentStart':
    case 'SubagentStop':
      return '🤖'
    case 'Stop':
      return '■'
    default:
      return '○'
  }
})

const toolName = computed(() => {
  if (props.event.subkind !== 'PreToolUse' && props.event.subkind !== 'PostToolUse') return null
  const detail = spy.detailCache[props.event.id]
  const payload = detail?.payload as { tool_name?: unknown } | undefined
  if (typeof payload?.tool_name === 'string') return payload.tool_name
  // il server mette il tool_name nello snippet degli hook Pre/PostToolUse
  const snippet = props.event.snippet
  return snippet && snippet !== props.event.subkind ? snippet : null
})

function onClick() {
  void spy.select(props.event.id)
}
</script>

<template>
  <div
    class="hook-marker"
    :class="{ selected, prompt: isPrompt }"
    :data-event-id="event.id"
    @click="onClick"
  >
    <span class="icon">{{ glyph }}</span>
    <span class="subkind">{{ event.subkind || 'hook' }}</span>
    <span v-if="toolName" class="tool">
      <span class="tool-icon">{{ toolIcon(toolName) }}</span>{{ toolName }}
    </span>
    <span v-if="isPrompt && event.snippet" class="prompt-snippet">{{ event.snippet }}</span>
    <span class="time">{{ formatTime(event.ts_start) }}</span>
  </div>
</template>

<style scoped>
.hook-marker {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.15rem 0.5rem;
  color: var(--muted);
  font-size: 0.75rem;
  cursor: pointer;
}

.hook-marker:hover {
  color: var(--text);
}

.hook-marker.selected {
  color: var(--text);
}

/* il prompt utente apre un giro: più marcato degli altri hook */
.hook-marker.prompt {
  padding: 0.3rem 0.55rem;
  background-color: rgba(62, 207, 110, 0.08);
  border-radius: 5px;
  color: var(--text);
}

.hook-marker.prompt .icon,
.hook-marker.prompt .subkind {
  color: var(--accent-live);
}

.icon {
  color: var(--muted);
  line-height: 1;
}

.subkind {
  font-weight: 600;
}

.tool {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  color: var(--accent-live);
}

.tool-icon {
  font-size: 0.8rem;
  line-height: 1;
}

.prompt-snippet {
  flex: 1;
  min-width: 0;
  color: var(--text);
  font-style: italic;
  opacity: 0.9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}
</style>
