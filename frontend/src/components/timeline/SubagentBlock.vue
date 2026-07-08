<script setup lang="ts">
// Pointer row for a sub-agent: does NOT render the child's own events, just a
// badge that links to the child session (once known — it can arrive via WS a
// moment after the event that first references it). Shows the sub-tree's
// total tokens (usage_incl_children) when the session is already known.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatTime, formatTokens } from '../../utils/format'
import { SUBAGENT_CAPTION } from '../../utils/caption'

const props = defineProps<{
  data: {
    agentId: string
    childId: string | null
    ts: number
    label: string
  }
}>()

const spy = useSpyStore()

const childTokens = computed<number | null>(() => {
  if (!props.data.childId) return null
  const s = spy.sessions[props.data.childId]
  if (!s) return null
  const u = s.usage_incl_children
  return u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
})
</script>

<template>
  <div class="rt-row subagent-row">
    <div class="col col-user">
      <div class="badge">
        <span class="badge-icon">🤖</span>
        <span class="badge-label">SUB-<br />AGENT</span>
      </div>
    </div>
    <div class="col col-claude">
      <p class="caption">💡 {{ SUBAGENT_CAPTION }}</p>
    </div>
    <div class="col col-tools">
      <component
        :is="data.childId ? 'router-link' : 'div'"
        class="tool-chip tool-chip--agent"
        :class="{ pending: !data.childId }"
        :to="data.childId ? `/session/${data.childId}` : undefined"
        :title="!data.childId ? `agent_id: ${data.agentId}` : undefined"
      >
        <span class="tool-icon">🤖</span>
        <span class="tool-name">{{ data.label }}</span>
        <span v-if="childTokens != null" class="tool-hint">{{ formatTokens(childTokens) }} tok</span>
        <span v-else class="tool-hint">{{ formatTime(data.ts) }}</span>
        <span v-if="data.childId" class="go">→</span>
      </component>
    </div>
  </div>
</template>

<style scoped>
.rt-row {
  display: grid;
  grid-template-columns: 130px 1fr 230px;
  gap: 10px;
  padding: 12px 0;
  border-bottom: 1px dashed var(--border);
  align-items: center;
}

.badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  background-color: color-mix(in srgb, var(--c-assistant) 14%, var(--panel-alt));
  border: 1px solid color-mix(in srgb, var(--c-assistant) 38%, var(--border));
  border-radius: 10px;
  padding: 10px 4px;
  font-size: 20px;
}

.badge-label {
  font-size: 8.5px;
  color: var(--muted-faint);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  text-align: center;
  line-height: 1.2;
}

.caption {
  font-size: 12px;
  font-style: italic;
  color: var(--muted-faint);
  max-width: 60ch;
}

.tool-chip--agent {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  background-color: color-mix(in srgb, var(--c-assistant) 14%, var(--panel-alt));
  border: 1px solid color-mix(in srgb, var(--c-assistant) 38%, var(--border));
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
  color: color-mix(in srgb, var(--c-assistant) 60%, var(--text));
  text-decoration: none;
  cursor: pointer;
}

.tool-chip--agent.pending {
  cursor: default;
  opacity: 0.75;
}

.tool-chip--agent:not(.pending):hover {
  border-color: var(--c-assistant);
}

.tool-name {
  font-weight: 600;
}

.tool-hint {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  color: color-mix(in srgb, var(--c-assistant) 65%, var(--muted));
  font-size: 11px;
}

.go {
  margin-left: auto;
  font-weight: 700;
  color: var(--c-assistant);
}
</style>
