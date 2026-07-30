<script setup lang="ts">
/**
 * Grid of key metrics for a session, plus sub-agent totals. Shared by the
 * dashboard and the timeline (SessionSummaryBar), so the "numbers" read the
 * same everywhere. Real data only: no counterfactual estimates.
 *
 * With the timeline paused, the session cards describe the run *up to the
 * player's position* (`cursorTs`) and show what the round trip under the
 * cursor added — that is how you see what a single step costs against the
 * whole. The sub-agent row stays the run's final total: the cut is deliberately
 * about the session you are stepping through, not its children.
 */
import { computed } from 'vue'
import type { Session, StatsItem, Usage } from '../types'
import { cacheWriteTiers } from '../utils/cache'
import { formatTokens } from '../utils/format'
import { statsForEvent, statsUpTo } from '../utils/playhead'
import { estimateCost, formatCost } from '../utils/pricing'
import { aggregateUsage, consumedTokens, contextTokens, peakContext, totalConsumed } from '../utils/usage'

const props = defineProps<{
  stats: StatsItem[]
  model: string | null
  /** numero di prompt utente (hook UserPromptSubmit) della sessione. */
  promptCount: number
  /** subagenti (discendenti) della sessione. */
  subagents: Session[]
  /** la card sub-agents è cliccabile (emette jump-subagents); nella timeline no. */
  clickableSubagents?: boolean
  /** ts del player: le card della sessione si fermano lì. null/assente (LIVE,
   *  dashboard) = nessun taglio, comportamento di sempre. */
  cursorTs?: number | null
  /** id dell'evento sotto il cursore, per il contributo del singolo step. */
  cursorEventId?: number | null
  /** etichetta della posizione, es. "evento 12/59". */
  cursorLabel?: string | null
}>()

/** Round trip fino al player (tutti quando non c'è taglio). */
const stats = computed(() => statsUpTo(props.stats, props.cursorTs ?? null))

/** Il round trip su cui è fermo il player: null se il cursore è su un hook. */
const stepStat = computed(() => statsForEvent(props.stats, props.cursorEventId ?? null))

const atCursor = computed(() => props.cursorTs != null)

const emit = defineEmits<{ (e: 'jump-subagents'): void }>()

const peak = computed(() => peakContext(stats.value))

const consumed = computed(() => totalConsumed(stats.value))

const ratio = computed(() => (peak.value > 0 ? consumed.value / peak.value : 0))

const roundTrips = computed(() => stats.value.length)

/** Total round trips of the run: featured + all sub-agents. The "incl.
 *  sub-agents" row answers "how much did the whole run cost?", so it stays on
 *  the final totals even when the player cuts the session cards. */
const roundTripsInclSub = computed(() =>
  props.subagents.reduce((sum, s) => sum + s.round_trips, props.stats.length),
)

const subagentTokens = computed(() =>
  props.subagents.reduce((sum, s) => {
    const u = s.usage
    return sum + u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
  }, 0),
)

/** Total consumed including sub-agents: the run's true integral (untouched by
 *  the playhead, see roundTripsInclSub). */
const totalConsumedInclSub = computed(
  () => totalConsumed(props.stats) + subagentTokens.value,
)

/** Sub-agent cost, each priced with its own model's rates. */
const subagentCost = computed(() =>
  props.subagents.reduce((sum, s) => sum + estimateCost(s.usage, s.model ?? props.model), 0),
)

const featuredUsage = computed<Usage>(() => aggregateUsage(stats.value))

const cost = computed(() => estimateCost(featuredUsage.value, props.model))

/** Costo dell'intera sessione, cursore o no: somma al costo dei sub-agenti per
 *  il totale del run. */
const costAll = computed(() => estimateCost(aggregateUsage(props.stats), props.model))

/** Contributo del round trip sotto il cursore: quanto è costato QUESTO step,
 *  la lettura didattica che il totale cumulato da solo non dà. */
const stepContribution = computed(() => {
  const s = stepStat.value
  if (!s || !atCursor.value) return null
  const usage: Usage = {
    input_tokens: s.input_tokens,
    output_tokens: s.output_tokens,
    cache_read_tokens: s.cache_read_tokens,
    cache_write_tokens: s.cache_write_tokens,
    cache_write_5m_tokens: s.cache_write_5m_tokens,
    cache_write_1h_tokens: s.cache_write_1h_tokens,
  }
  return {
    context: contextTokens(s),
    consumed: consumedTokens(s),
    cost: estimateCost(usage, s.model ?? props.model),
  }
})

/** Share of the cache writes per TTL: which caching strategy the session used
 *  (the two tiers cost differently, so the mix explains the cost too). */
const cacheTtlMix = computed(() => {
  const t = cacheWriteTiers(featuredUsage.value)
  const total = t.m5 + t.h1 + t.unknown
  if (total === 0) return null
  const parts: string[] = []
  if (t.h1 > 0) parts.push(`1h ${Math.round((t.h1 / total) * 100)}%`)
  if (t.m5 > 0) parts.push(`5m ${Math.round((t.m5 / total) * 100)}%`)
  if (t.unknown > 0) parts.push(`n/a ${Math.round((t.unknown / total) * 100)}%`)
  return { text: parts.join(' · '), total, tiers: t }
})
</script>

<template>
  <div class="metric-cards">
    <span class="group-label">
      Session
      <span v-if="atCursor && cursorLabel" class="at-cursor" :title="'Le card della sessione si fermano al punto del player: ' + cursorLabel">
        ❚❚ fino a {{ cursorLabel }}
      </span>
    </span>
    <div class="card">
      <span class="label"><span class="ic">📈</span>peak context</span>
      <span class="value">{{ formatTokens(peak) }}</span>
      <span v-if="stepContribution" class="step-note">
        questo step: {{ formatTokens(stepContribution.context) }}
      </span>
    </div>
    <div class="card">
      <span class="label"><span class="ic">🧮</span>tokens consumed (integral)</span>
      <span class="value">{{ formatTokens(consumed) }}</span>
      <span v-if="stepContribution" class="step-note">
        +{{ formatTokens(stepContribution.consumed) }} questo step
      </span>
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
    <div v-if="cacheTtlMix" class="card">
      <span class="label">
        <span class="ic">⏱️</span>cache write TTL · {{ formatTokens(cacheTtlMix.total) }} tok
      </span>
      <span class="value value--mix">{{ cacheTtlMix.text }}</span>
    </div>
    <div class="card">
      <span class="label"><span class="ic">💰</span>estimated cost</span>
      <span class="value">{{ formatCost(cost) }}</span>
      <span v-if="stepContribution" class="step-note">
        +{{ formatCost(stepContribution.cost) }} questo step
      </span>
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
           che risponde a "quanto è costato tutto?", quindi non attenuato e non
           tagliato dal player -->
      <div class="card card--total">
        <span class="label"><span class="ic">💰</span>total cost (incl. sub-agents)</span>
        <span class="value">{{ formatCost(costAll + subagentCost) }}</span>
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

/* posizione del player accanto al titolo del gruppo: chiarisce che i numeri
   sotto non sono il totale della sessione ma il cumulato fino a lì */
.at-cursor {
  margin-left: 0.4rem;
  padding: 0.05rem 0.35rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background-color: var(--panel);
  color: var(--muted);
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0;
  white-space: nowrap;
}

/* contributo del singolo round trip sotto il cursore */
.step-note {
  font-size: 0.65rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* "1h 68% · 5m 32%": due valori in una card, quindi un filo più compatto */
.value--mix {
  font-size: 0.8rem;
  white-space: nowrap;
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
