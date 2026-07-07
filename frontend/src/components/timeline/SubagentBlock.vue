<script setup lang="ts">
// Blocco di rimando per un subagente: NON renderizza gli eventi del figlio,
// solo una card che invita al click e naviga alla sessione figlia (se già
// nota: può arrivare via WS con qualche istante di ritardo rispetto al primo
// evento che la referenzia). Se la sessione figlia è nota mostra anche i
// token complessivi del sotto-albero (usage_incl_children), letti dallo store.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatTime, formatTokens } from '../../utils/format'

const props = defineProps<{
  data: {
    agentId: string
    childId: string | null
    ts: number
    label: string
  }
}>()

const spy = useSpyStore()

/** Token totali del sotto-albero del figlio, se la sessione è già nota. */
const childTokens = computed<number | null>(() => {
  if (!props.data.childId) return null
  const s = spy.sessions[props.data.childId]
  if (!s) return null
  const u = s.usage_incl_children
  return u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
})
</script>

<template>
  <component
    :is="data.childId ? 'router-link' : 'div'"
    class="subagent-block"
    :class="{ pending: !data.childId }"
    :to="data.childId ? `/session/${data.childId}` : undefined"
    :title="!data.childId ? `agent_id: ${data.agentId}` : undefined"
  >
    <span class="icon">🤖</span>
    <div class="body">
      <span class="name">Subagente {{ data.label }}</span>
      <span v-if="!data.childId" class="note">sessione non ancora nota</span>
    </div>
    <span v-if="childTokens != null" class="tokens">{{ formatTokens(childTokens) }} tok</span>
    <span class="time">{{ formatTime(data.ts) }}</span>
    <span v-if="data.childId" class="go">→</span>
  </component>
</template>

<style scoped>
.subagent-block {
  --sa-accent: #f0883e;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.45rem 0.7rem;
  background-color: rgba(240, 136, 62, 0.09);
  border: 1px solid rgba(240, 136, 62, 0.45);
  border-left: 3px solid var(--sa-accent);
  border-radius: 6px;
  font-size: 0.8rem;
  text-decoration: none;
  color: var(--text);
  cursor: pointer;
}

.subagent-block:not(.pending):hover {
  background-color: rgba(240, 136, 62, 0.16);
  border-color: var(--sa-accent);
}

.subagent-block.pending {
  cursor: default;
  opacity: 0.75;
}

.icon {
  font-size: 0.95rem;
  line-height: 1;
}

.body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
  min-width: 0;
}

.name {
  font-weight: 600;
  color: var(--sa-accent);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note {
  font-size: 0.68rem;
  font-style: italic;
  color: var(--muted);
}

.tokens,
.time {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  font-size: 0.72rem;
}

.go {
  color: var(--sa-accent);
  font-weight: 700;
}
</style>
