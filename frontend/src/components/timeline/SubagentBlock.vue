<script setup lang="ts">
// Blocco di rimando per un subagente: NON renderizza gli eventi del figlio,
// solo un indicatore indentato con link alla sessione figlia (se già nota:
// la sessione figlia può arrivare via WS con qualche istante di ritardo
// rispetto al primo evento che la referenzia).
import { formatTime } from '../../utils/format'

defineProps<{
  data: {
    agentId: string
    childId: string | null
    ts: number
    label: string
  }
}>()
</script>

<template>
  <div class="subagent-block">
    <span class="branch">↳</span>
    <router-link v-if="data.childId" class="link" :to="`/session/${data.childId}`">
      Subagente {{ data.label }}
    </router-link>
    <span v-else class="pending" :title="`agent_id: ${data.agentId}`">
      Subagente {{ data.label }} (sessione non ancora nota)
    </span>
    <span class="time">{{ formatTime(data.ts) }}</span>
  </div>
</template>

<style scoped>
.subagent-block {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: 1.1rem;
  padding: 0.3rem 0.6rem;
  border-left: 2px dashed var(--muted);
  font-size: 0.78rem;
}

.branch {
  color: var(--muted);
}

.link {
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
}

.link:hover {
  text-decoration: underline;
}

.pending {
  color: var(--muted);
  font-style: italic;
}

.time {
  margin-left: auto;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
</style>
