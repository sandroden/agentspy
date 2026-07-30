<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useSessionStats } from '../composables/useSessionStats'
import { useSpyStore } from '../stores/spy'
import { formatTime, formatTokens } from '../utils/format'
import { statsForEvent, statsUpTo } from '../utils/playhead'
import { estimateCost, formatCost } from '../utils/pricing'
import { aggregateUsage, consumedTokens, totalConsumed } from '../utils/usage'

const spy = useSpyStore()

const { session, stats } = useSessionStats()

const total = computed(() => spy.events.length)
const maxIndex = computed(() => Math.max(total.value - 1, 0))
const currentIndex = computed(() => Math.min(Math.max(spy.cursor, 0), maxIndex.value))
const currentEvent = computed(() => spy.events[currentIndex.value] ?? null)

/** Counter AND scrubber work on the player's real steps, not on the raw
 * indices of `events`: with the hooks hidden the raw indices would jump
 * (event 3/15 → 5/15) and the scrubber knob would never start from the
 * edge (⏮ lands on the first round trip, which in raw indices is already
 * a third of the way along the bar). The computation lives in the store
 * because the timeline metrics share it (see MetricCards). */
const stepIndices = computed(() => spy.playerSteps)
const stepTotal = computed(() => spy.playerPosition.total)
const currentStep = computed(() => spy.playerPosition.index)

const label = computed(() => {
  if (stepTotal.value === 0) return 'no events'
  return `event ${currentStep.value + 1}/${stepTotal.value} — ${formatTime(currentEvent.value?.ts_start)}`
})

/**
 * Tokens and cost at the point we are on, compact and ALWAYS visible: the
 * MetricCards scroll out of the viewport as soon as the timeline moves on,
 * while this bar is sticky. Same source and same helpers as the cards
 * (utils/usage + utils/playhead), so the numbers cannot diverge.
 */
const upToCursor = computed(() =>
  statsUpTo(stats.value, spy.live ? null : (spy.cursorEvent?.ts_start ?? null))
)

const readout = computed(() => {
  if (upToCursor.value.length === 0) return null
  const model = session.value?.model ?? null
  const step = spy.live ? null : statsForEvent(stats.value, spy.cursorEvent?.id ?? null)
  return {
    tokens: totalConsumed(upToCursor.value),
    cost: estimateCost(aggregateUsage(upToCursor.value), model),
    stepTokens: step ? consumedTokens(step) : null,
    stepCost: step ? estimateCost(aggregateUsage([step]), step.model ?? model) : null,
  }
})

const readoutTitle = computed(() =>
  spy.live
    ? 'tokens consumed and estimated cost of the session (whole: the player is LIVE)'
    : 'tokens consumed and estimated cost up to the player position; in italics the contribution of this round trip'
)

function onSlider(e: Event) {
  const pos = Number((e.target as HTMLInputElement).value)
  const idx = stepIndices.value[pos]
  if (idx != null) spy.setCursor(idx)
}

function toggleLive() {
  if (spy.live) spy.pause()
  else spy.goLive()
}

function onKeydown(e: KeyboardEvent) {
  const target = e.target as HTMLElement | null
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
  if (e.code === 'Space') {
    e.preventDefault()
    toggleLive()
  } else if (e.code === 'ArrowLeft') {
    spy.step(-1)
  } else if (e.code === 'ArrowRight') {
    spy.step(1)
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="time-controls">
    <button class="live-btn" :class="{ live: spy.live }" @click="toggleLive">
      {{ spy.live ? '● LIVE' : '❚❚ PAUSED' }}
    </button>

    <button :disabled="total === 0" title="start" @click="spy.setCursor(0)">⏮</button>
    <button :disabled="total === 0" title="back" @click="spy.step(-1)">◀</button>
    <input
      class="scrubber"
      type="range"
      :min="0"
      :max="Math.max(stepTotal - 1, 0)"
      :value="currentStep"
      :disabled="total === 0"
      @input="onSlider"
    />
    <button :disabled="total === 0" title="forward" @click="spy.step(1)">▶</button>
    <button :disabled="total === 0" title="end" @click="spy.setCursor(maxIndex)">⏭</button>

    <span class="label">{{ label }}</span>

    <span v-if="readout" class="readout" :title="readoutTitle">
      <span class="ro-val">{{ formatTokens(readout.tokens) }}</span> tok ·
      <span class="ro-val">{{ formatCost(readout.cost) }}</span>
      <em v-if="readout.stepTokens != null">
        (+{{ formatTokens(readout.stepTokens) }} · +{{ formatCost(readout.stepCost ?? 0) }})
      </em>
    </span>

    <button
      class="hooks-btn"
      :class="{ on: spy.showHooks }"
      title="show Claude Code hooks as markers in the timeline (the player stops skipping them)"
      @click="spy.toggleShowHooks()"
    >
      ⚓︎ hooks
    </button>
  </div>
</template>

<style scoped>
.time-controls {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background-color: var(--panel);
  border-bottom: 1px solid var(--border);
}

button {
  background-color: var(--panel-alt);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.3rem 0.6rem;
  cursor: pointer;
  font-size: 0.85rem;
}

button:disabled {
  opacity: 0.4;
  cursor: default;
}

.live-btn.live {
  background-color: var(--accent-live);
  color: #06210f;
  border-color: var(--accent-live);
}

.hooks-btn {
  color: var(--muted);
  border-style: dashed;
  white-space: nowrap;
}

.hooks-btn.on {
  color: var(--text);
  border-style: solid;
  border-color: var(--muted);
}

.scrubber {
  flex: 1;
}

.label {
  white-space: nowrap;
  color: var(--muted);
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
}

/* compact tokens/cost readout at the player position: it lives in the sticky
   bar because it is the number that must stay in sight while scrolling */
.readout {
  white-space: nowrap;
  color: var(--muted);
  font-size: 0.78rem;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  padding: 0.15rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background-color: var(--panel-alt);
}

.readout .ro-val {
  color: var(--text);
  font-weight: 700;
}

/* current round trip's contribution: present but subordinate to the cumulative */
.readout em {
  font-style: normal;
  opacity: 0.75;
}
</style>
