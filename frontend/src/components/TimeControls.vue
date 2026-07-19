<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useSpyStore } from '../stores/spy'
import { formatTime } from '../utils/format'

const spy = useSpyStore()

const total = computed(() => spy.events.length)
const maxIndex = computed(() => Math.max(total.value - 1, 0))
const currentIndex = computed(() => Math.min(Math.max(spy.cursor, 0), maxIndex.value))
const currentEvent = computed(() => spy.events[currentIndex.value] ?? null)

/** Contatore E scrubber lavorano sugli step veri del player, non sugli
 * indici grezzi di `events`: con gli hook nascosti gli indici grezzi
 * salterebbero (event 3/15 → 5/15) e il pallino dello scrubber non
 * partirebbe mai dal bordo (⏮ atterra sul primo round trip, che negli
 * indici grezzi è già a un terzo della barra). */
const stepIndices = computed<number[]>(() => {
  const out: number[] = []
  spy.events.forEach((e, i) => {
    if (spy.isPlayerStep(e)) out.push(i)
  })
  return out
})
const stepTotal = computed(() => stepIndices.value.length)
/** posizione 0-based dello step corrente: ultimo step con indice ≤ cursore. */
const currentStep = computed(() => {
  let pos = -1
  for (const idx of stepIndices.value) {
    if (idx > currentIndex.value) break
    pos++
  }
  return Math.max(pos, 0)
})

const label = computed(() => {
  if (stepTotal.value === 0) return 'no events'
  return `event ${currentStep.value + 1}/${stepTotal.value} — ${formatTime(currentEvent.value?.ts_start)}`
})

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

    <button
      class="hooks-btn"
      :class="{ on: spy.showHooks }"
      title="mostra gli hook di Claude Code come marcatori nella timeline (il player smette di saltarli)"
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
</style>
