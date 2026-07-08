<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useSpyStore } from '../stores/spy'
import { formatTime } from '../utils/format'

const spy = useSpyStore()

const total = computed(() => spy.events.length)
const maxIndex = computed(() => Math.max(total.value - 1, 0))
const currentIndex = computed(() => Math.min(Math.max(spy.cursor, 0), maxIndex.value))
const currentEvent = computed(() => spy.events[currentIndex.value] ?? null)

const label = computed(() => {
  if (total.value === 0) return 'no events'
  return `event ${currentIndex.value + 1}/${total.value} — ${formatTime(currentEvent.value?.ts_start)}`
})

function onSlider(e: Event) {
  spy.setCursor(Number((e.target as HTMLInputElement).value))
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
      :max="maxIndex"
      :value="currentIndex"
      :disabled="total === 0"
      @input="onSlider"
    />
    <button :disabled="total === 0" title="forward" @click="spy.step(1)">▶</button>
    <button :disabled="total === 0" title="end" @click="spy.setCursor(maxIndex)">⏭</button>

    <span class="label">{{ label }}</span>
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
