<script setup lang="ts">
/**
 * Griglia di metriche chiave della sessione in evidenza (featured), più i
 * totali dei subagenti. Solo dati reali: nessuna stima controfattuale.
 */
import { computed } from 'vue'
import type { Session, StatsItem, Usage } from '../../types'
import { formatTokens } from '../../utils/format'
import { estimateCost, formatCost } from '../../utils/pricing'

const props = defineProps<{
  stats: StatsItem[]
  model: string | null
  /** numero di prompt utente (hook UserPromptSubmit) della featured. */
  promptCount: number
  /** subagenti (discendenti) della featured. */
  subagents: Session[]
}>()

const emit = defineEmits<{ (e: 'jump-subagents'): void }>()

/** Token "in contesto" per un round trip: input nuovo + cache letta + cache scritta. */
function contextTokens(s: StatsItem): number {
  return s.input_tokens + s.cache_read_tokens + s.cache_write_tokens
}

/** Token consumati (contributo all'integrale): contesto + output. */
function consumedTokens(s: StatsItem): number {
  return contextTokens(s) + s.output_tokens
}

const peakContext = computed(() =>
  props.stats.length ? Math.max(...props.stats.map(contextTokens)) : 0
)

const totalConsumed = computed(() => props.stats.reduce((sum, s) => sum + consumedTokens(s), 0))

const ratio = computed(() =>
  peakContext.value > 0 ? totalConsumed.value / peakContext.value : 0
)

const roundTrips = computed(() => props.stats.length)

const subagentTokens = computed(() =>
  props.subagents.reduce((sum, s) => {
    const u = s.usage
    return sum + u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
  }, 0)
)

const featuredUsage = computed<Usage>(() =>
  props.stats.reduce(
    (acc, s) => ({
      input_tokens: acc.input_tokens + s.input_tokens,
      output_tokens: acc.output_tokens + s.output_tokens,
      cache_read_tokens: acc.cache_read_tokens + s.cache_read_tokens,
      cache_write_tokens: acc.cache_write_tokens + s.cache_write_tokens,
    }),
    { input_tokens: 0, output_tokens: 0, cache_read_tokens: 0, cache_write_tokens: 0 }
  )
)

const cost = computed(() => estimateCost(featuredUsage.value, props.model))
</script>

<template>
  <div class="metric-cards">
    <div class="card">
      <div class="value">{{ formatTokens(peakContext) }}</div>
      <div class="label">contesto di picco</div>
    </div>
    <div class="card">
      <div class="value">{{ formatTokens(totalConsumed) }}</div>
      <div class="label">token consumati (integrale)</div>
    </div>
    <div class="card">
      <div class="value">{{ ratio > 0 ? ratio.toFixed(1) + '×' : '—' }}</div>
      <div class="label">consumo / picco</div>
    </div>
    <div class="card">
      <div class="value">{{ promptCount }}</div>
      <div class="label">prompt utente</div>
    </div>
    <div class="card">
      <div class="value">{{ roundTrips }}</div>
      <div class="label">round trip</div>
    </div>
    <div
      class="card"
      :class="{ clickable: subagents.length > 0 }"
      @click="subagents.length > 0 && emit('jump-subagents')"
    >
      <div class="value">{{ subagents.length }}</div>
      <div class="label">
        subagenti<template v-if="subagents.length">
          · {{ formatTokens(subagentTokens) }} tok</template
        >
      </div>
    </div>
    <div class="card">
      <div class="value">{{ formatCost(cost) }}</div>
      <div class="label">costo stimato (featured)</div>
    </div>
  </div>
</template>

<style scoped>
.metric-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;
}

.card {
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.9rem 1rem;
}

.card.clickable {
  cursor: pointer;
}

.card.clickable:hover {
  border-color: var(--accent);
}

.value {
  font-size: 1.6rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text);
  line-height: 1.1;
}

.label {
  margin-top: 0.35rem;
  font-size: 0.75rem;
  color: var(--muted);
}
</style>
