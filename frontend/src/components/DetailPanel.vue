<script setup lang="ts">
// CONTRATTO (implementazione vera in un altro agente F4b): legge
// `selectedEventId` e `selectedDetail` (getter, EventDetail | null, lazy-fetch
// con cache in `detailCache`/`detailLoading`) dallo store spy. Il pannello a
// tab (Sintesi | Richiesta | Risposta | Delta | JSON grezzo) userà
// selectedDetail.payload. Montato da App.vue, visibile solo quando
// selectedEventId != null. Questo è solo un placeholder.
import { useSpyStore } from '../stores/spy'

const spy = useSpyStore()
</script>

<template>
  <div class="detail-panel">
    <p v-if="spy.selectedEventId == null" class="placeholder">Nessun evento selezionato</p>
    <template v-else>
      <p class="placeholder">DetailPanel (stub) — evento #{{ spy.selectedEventId }}</p>
      <p v-if="!spy.selectedDetail" class="placeholder">caricamento dettaglio…</p>
    </template>
  </div>
</template>

<style scoped>
.detail-panel {
  padding: 1rem;
}

.placeholder {
  color: var(--muted);
  font-style: italic;
}
</style>
