<script setup lang="ts">
/**
 * Grid of key metrics for a session, plus sub-agent totals. Shared by the
 * dashboard and the timeline (SessionSummaryBar), so the "numbers" read the
 * same everywhere. Real data only: no counterfactual estimates.
 */
import { computed } from 'vue'
import type { Session, StatsItem, Usage } from '../types'
import { formatTokens } from '../utils/format'
import { estimateCost, formatCost } from '../utils/pricing'

const props = defineProps<{
  stats: StatsItem[]
  model: string | null
  /** numero di prompt utente (hook UserPromptSubmit) della sessione. */
  promptCount: number
  /** subagenti (discendenti) della sessione. */
  subagents: Session[]
  /** la card sub-agents è cliccabile (emette jump-subagents); nella timeline no. */
  clickableSubagents?: boolean
}>()

const emit = defineEmits<{ (e: 'jump-subagents'): void }>()

/** Tokens "in context" for a round trip: new input + cache read + cache write. */
function contextTokens(s: StatsItem): number {
  return s.input_tokens + s.cache_read_tokens + s.cache_write_tokens
}

/** Tokens consumed (contribution to the integral): context + output. */
function consumedTokens(s: StatsItem): number {
  return contextTokens(s) + s.output_tokens
}

const peakContext = computed(() =>
  props.stats.length ? Math.max(...props.stats.map(contextTokens)) : 0,
)

const totalConsumed = computed(() => props.stats.reduce((sum, s) => sum + consumedTokens(s), 0))

const ratio = computed(() => (peakContext.value > 0 ? totalConsumed.value / peakContext.value : 0))

const roundTrips = computed(() => props.stats.length)

/** Total round trips of the run: featured + all sub-agents. */
const roundTripsInclSub = computed(() =>
  props.subagents.reduce((sum, s) => sum + s.round_trips, roundTrips.value),
)

const subagentTokens = computed(() =>
  props.subagents.reduce((sum, s) => {
    const u = s.usage
    return sum + u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
  }, 0),
)

/** Total consumed including sub-agents: the run's true integral. */
const totalConsumedInclSub = computed(() => totalConsumed.value + subagentTokens.value)

/** Sub-agent cost, each priced with its own model's rates. */
const subagentCost = computed(() =>
  props.subagents.reduce((sum, s) => sum + estimateCost(s.usage, s.model ?? props.model), 0),
)

const featuredUsage = computed<Usage>(() =>
  props.stats.reduce(
    (acc, s) => ({
      input_tokens: acc.input_tokens + s.input_tokens,
      output_tokens: acc.output_tokens + s.output_tokens,
      cache_read_tokens: acc.cache_read_tokens + s.cache_read_tokens,
      cache_write_tokens: acc.cache_write_tokens + s.cache_write_tokens,
    }),
    {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
    },
  ),
)

const cost = computed(() => estimateCost(featuredUsage.value, props.model))
</script>

<template>
  <div class="metric-cards">
    <span class="group-label">Session</span>
    <div class="card">
      <span class="label"><span class="ic">📈</span>peak context</span>
      <span class="value">{{ formatTokens(peakContext) }}</span>
    </div>
    <div class="card">
      <span class="label"><span class="ic">🧮</span>tokens consumed (integral)</span>
      <span class="value">{{ formatTokens(totalConsumed) }}</span>
    </div>
    <div class="card">
      <span class="label"><span class="ic">⚖️</span>consumption / peak</span>
      <span class="value">{{ ratio > 0 ? ratio.toFixed(1) + '×' : '—' }}</span>
    </div>
    <div class="card">
      <span class="label"><span class="ic">💬</span>user prompts</span>
      <span class="value">{{ promptCount }}</span>
    </div>
    <div class="card">
      <span class="label"><span class="ic">🔁</span>round trips</span>
      <span class="value">{{ roundTrips }}</span>
    </div>
    <div
      class="card"
      :class="{ clickable: clickableSubagents && subagents.length > 0 }"
      @click="clickableSubagents && subagents.length > 0 && emit('jump-subagents')"
    >
      <span class="label">
        <span class="ic">🤖</span>sub-agents<template v-if="subagents.length">
          · {{ formatTokens(subagentTokens) }} tok</template
        >
      </span>
      <span class="value">{{ subagents.length }}</span>
    </div>
    <div class="card">
      <span class="label"><span class="ic">💰</span>estimated cost</span>
      <span class="value">{{ formatCost(cost) }}</span>
    </div>

    <template v-if="subagents.length">
      <span class="group-label group-label--sub">total · incl. sub-agents</span>
      <div class="card card--sub">
        <span class="label"><span class="ic">🧮</span>tokens consumed (integral)</span>
        <span class="value">{{ formatTokens(totalConsumedInclSub) }}</span>
      </div>
      <div class="card card--sub">
        <span class="label"><span class="ic">🔁</span>round trips</span>
        <span class="value">{{ roundTripsInclSub }}</span>
      </div>
      <!-- il costo dell'intero run (sessione + tutti i sub-agent): il numero
           che risponde a "quanto è costato tutto?", quindi non attenuato -->
      <div class="card card--total">
        <span class="label"><span class="ic">💰</span>total cost (incl. sub-agents)</span>
        <span class="value">{{ formatCost(cost + subagentCost) }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.metric-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.group-label {
  font: 700 0.65rem system-ui;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted-faint);
  margin-right: 0.1rem;
}

.group-label--sub {
  flex-basis: 100%;
  margin-top: 0.4rem;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.3rem 0.6rem;
  min-width: 90px;
}

.card--sub {
  opacity: 0.65;
  padding: 0.25rem 0.5rem;
  min-width: auto;
}

/* costo totale del run: pieno risalto, bordo accent */
.card--total {
  border-color: var(--accent);
}

.card.clickable {
  cursor: pointer;
}

.card.clickable:hover {
  border-color: var(--accent);
}

.value {
  font-size: 0.9rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text);
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}

.label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--muted-faint);
}

/* piccola icona davanti all'etichetta della card */
.ic {
  margin-right: 0.25rem;
  font-size: 0.7rem;
}
</style>
