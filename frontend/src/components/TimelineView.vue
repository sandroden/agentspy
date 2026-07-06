<script setup lang="ts">
// CONTRATTO (implementazione vera in un altro agente F4b): legge
// `visibleEvents` (getter, EventSummary[]) dallo store spy per il rendering
// della timeline verticale raggruppata per turno (turn_index), con subagenti
// annidati/indentati e click su evento -> spy.select(id). Questo è solo un
// placeholder con il conteggio.
import { useSpyStore } from '../stores/spy'

const spy = useSpyStore()
</script>

<template>
  <div class="timeline-view">
    <p class="placeholder">
      TimelineView (stub) — {{ spy.visibleEvents.length }} eventi visibili su
      {{ spy.events.length }} totali
    </p>
  </div>
</template>

<style scoped>
.timeline-view {
  flex: 1;
  padding: 1rem 1.5rem;
}

.placeholder {
  color: var(--muted);
  font-style: italic;
}
</style>
