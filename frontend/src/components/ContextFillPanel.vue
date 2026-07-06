<script setup lang="ts">
// CONTRATTO (implementazione vera in un altro agente F4b): legge `stats`
// (StatsItem[]) dallo store spy per la sessione aperta, per disegnare la
// barra impilata system/tools/storia/nuovo (char/4 stimati) con overlay dei
// valori reali di usage (cache_read/write/input/output). Montato/smontato da
// SessionView tramite il toggle "mostra riempimento contesto". Questo è solo
// un placeholder.
import { useSpyStore } from '../stores/spy'

const spy = useSpyStore()
</script>

<template>
  <div class="context-fill-panel">
    <p class="placeholder">ContextFillPanel (stub) — {{ spy.stats.length }} punti stats</p>
  </div>
</template>

<style scoped>
.context-fill-panel {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
}

.placeholder {
  color: var(--muted);
  font-style: italic;
}
</style>
