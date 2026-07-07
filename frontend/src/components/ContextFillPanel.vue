<script setup lang="ts">
// Vista "riempimento del contesto": una barra orizzontale impilata per ogni
// round trip della sessione aperta (spy.stats), in ordine temporale come la
// timeline. La larghezza totale è proporzionale a input+cache_read+cache_write
// (scala comune = max della sessione); segmenti cache_read/cache_write/nuovo
// più una tacca separata per l'output. Click su una barra -> spy.select(id).
import { computed } from 'vue'
import { useSpyStore } from '../stores/spy'
import type { StatsItem } from '../types'
import { formatTime, formatTokens } from '../utils/format'

const spy = useSpyStore()

const stats = computed(() => spy.stats)

function contextSize(s: StatsItem): number {
  return s.input_tokens + s.cache_read_tokens + s.cache_write_tokens
}

const maxContext = computed(() => Math.max(1, ...stats.value.map(contextSize)))
const maxOutput = computed(() => Math.max(1, ...stats.value.map((s) => s.output_tokens)))

function pct(n: number): string {
  return `${((n / maxContext.value) * 100).toFixed(3)}%`
}

function outputPct(n: number): string {
  return `${((n / maxOutput.value) * 100).toFixed(3)}%`
}

/** Modello abbreviato per non affollare l'etichetta laterale (vedi SessionsSidebar). */
function abbreviateModel(model: string | null): string {
  if (!model) return '—'
  const m = model.match(/claude-([a-z]+)-(\d+)(?:-(\d+))?/)
  if (m) {
    const [, family, major, minor] = m
    return minor ? `${family}-${major}.${minor}` : `${family}-${major}`
  }
  return model.length > 14 ? `${model.slice(0, 14)}…` : model
}

function tooltip(s: StatsItem): string {
  const lines = [
    `input nuovo: ${s.input_tokens} token`,
    `cache_read: ${s.cache_read_tokens} token`,
    `cache_write: ${s.cache_write_tokens} token`,
    `output: ${s.output_tokens} token`,
  ]
  if (s.system_chars != null) lines.push(`system: ~${s.system_chars} char`)
  if (s.tools_chars != null) lines.push(`tools: ~${s.tools_chars} char`)
  if (s.messages_chars != null) lines.push(`messages: ~${s.messages_chars} char`)
  return lines.join('\n')
}

// -- totali di sessione ------------------------------------------------------

const totalOutput = computed(() => stats.value.reduce((sum, s) => sum + s.output_tokens, 0))
const totalNewInput = computed(() => stats.value.reduce((sum, s) => sum + s.input_tokens, 0))
const lastContext = computed(() => {
  const last = stats.value[stats.value.length - 1]
  return last ? contextSize(last) : 0
})

function select(eventId: number) {
  void spy.select(eventId)
}
</script>

<template>
  <div class="context-fill-panel">
    <p v-if="stats.length === 0" class="empty">
      Nessun round trip ancora in questa sessione.
    </p>
    <template v-else>
      <div class="summary">
        <div class="summary-row">
          <span>output totale <b>{{ formatTokens(totalOutput) }}</b></span>
          <span>input nuovo totale <b>{{ formatTokens(totalNewInput) }}</b></span>
          <span>contesto attuale <b>{{ formatTokens(lastContext) }}</b></span>
        </div>
        <p class="hint">
          La parte fredda (cache_read) è già servita dalla cache: costa e pesa meno di rigenerarla;
          la parte accesa è testo nuovo mandato per la prima volta.
        </p>
      </div>

      <div class="legend">
        <span class="legend-item"><i class="swatch cache-read"></i>cache_read</span>
        <span class="legend-item"><i class="swatch cache-write"></i>cache_write</span>
        <span class="legend-item"><i class="swatch new"></i>nuovo</span>
        <span class="legend-item"><i class="swatch output"></i>output</span>
      </div>

      <div class="bars">
        <div
          v-for="s in stats"
          :key="s.event_id"
          class="bar-row"
          @click="select(s.event_id)"
        >
          <div class="label">
            <span class="turn">T{{ s.turn_index ?? '—' }}</span>
            <span class="time">{{ formatTime(s.ts_start) }}</span>
            <span class="model">{{ abbreviateModel(s.model) }}</span>
          </div>
          <div class="bar-track" :title="tooltip(s)">
            <div class="segment cache-read" :style="{ width: pct(s.cache_read_tokens) }"></div>
            <div class="segment cache-write" :style="{ width: pct(s.cache_write_tokens) }"></div>
            <div class="segment new" :style="{ width: pct(s.input_tokens) }"></div>
          </div>
          <div class="output-track" :title="tooltip(s)">
            <div class="output-tick" :style="{ width: outputPct(s.output_tokens) }"></div>
          </div>
          <div class="total">{{ formatTokens(contextSize(s)) }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.context-fill-panel {
  padding: 0.75rem 1.5rem 1rem;
  border-bottom: 1px solid var(--border);
  --cf-cache-read: #4a5a72;
  --cf-cache-write: #4f8aa3;
  --cf-new: #e0a23d;
  --cf-output: #b06fd6;
}

.empty {
  color: var(--muted);
  font-style: italic;
}

.summary {
  margin-bottom: 0.5rem;
}

.summary-row {
  display: flex;
  gap: 1.4rem;
  font-size: 0.85rem;
  color: var(--muted);
}

.summary-row b {
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.hint {
  margin-top: 0.3rem;
  font-size: 0.78rem;
  color: var(--muted);
  font-style: italic;
  max-width: 60ch;
}

.legend {
  display: flex;
  gap: 0.9rem;
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 0.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.swatch {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 2px;
}

.swatch.cache-read {
  background-color: var(--cf-cache-read);
}

.swatch.cache-write {
  background-color: var(--cf-cache-write);
}

.swatch.new {
  background-color: var(--cf-new);
}

.swatch.output {
  background-color: var(--cf-output);
}

.bars {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  padding: 0.15rem 0.2rem;
  border-radius: 3px;
}

.bar-row:hover {
  background-color: var(--panel-alt);
}

.label {
  flex: none;
  width: 150px;
  display: flex;
  gap: 0.35rem;
  font-size: 0.72rem;
  color: var(--muted);
  overflow: hidden;
}

.label .turn {
  color: var(--text);
  font-weight: 600;
}

.bar-track {
  flex: 1;
  display: flex;
  height: 13px;
  background-color: var(--panel-alt);
  border-radius: 2px;
  overflow: hidden;
}

.segment {
  height: 100%;
}

.segment.cache-read {
  background-color: var(--cf-cache-read);
}

.segment.cache-write {
  background-color: var(--cf-cache-write);
}

.segment.new {
  background-color: var(--cf-new);
}

.output-track {
  flex: none;
  width: 50px;
  height: 13px;
  background-color: var(--panel-alt);
  border-radius: 2px;
  overflow: hidden;
}

.output-tick {
  height: 100%;
  background-color: var(--cf-output);
}

.total {
  flex: none;
  width: 55px;
  text-align: right;
  font-size: 0.72rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
</style>
