<script setup lang="ts">
/**
 * "Cumulative consumption (integral)": running sum of tokens consumed per
 * round trip of the featured session (input + cache + output). Dragging
 * horizontally selects a band: the readout shows tokens consumed in that
 * interval (difference of the cumulative) and the cost estimate. Checkbox to
 * overlay the other top-level sessions.
 */
import { computed, ref } from 'vue'
import type { Session, StatsItem, Usage } from '../../types'
import { useElementWidth } from '../../composables/useElementSize'
import { formatTokens } from '../../utils/format'
import { estimateCost, formatCost } from '../../utils/pricing'

interface Series {
  session: Session
  stats: StatsItem[]
  featured: boolean
  /** descendants of the featured family: always visible, dashed. */
  subagent?: boolean
}

const props = defineProps<{
  series: Series[]
  featuredModel: string | null
}>()

const el = ref<HTMLElement | null>(null)
const width = useElementWidth(el, 680)
const height = 260
const margin = { top: 14, right: 16, bottom: 26, left: 52 }

const showOthers = ref(false)

function consumed(s: StatsItem): number {
  return s.input_tokens + s.cache_read_tokens + s.cache_write_tokens + s.output_tokens
}

const featured = computed(() => props.series.find((s) => s.featured) ?? null)

/** cumulative[i] = sum of consumption up to and including round trip i. */
function cumulativeOf(stats: StatsItem[]): number[] {
  const out: number[] = []
  let acc = 0
  for (const s of stats) {
    acc += consumed(s)
    out.push(acc)
  }
  return out
}

/** The featured session and its family's subagents are always visible; other
 * top-level sessions only show up with the checkbox. */
const shownSeries = computed(() =>
  props.series.filter(
    (s) => (s.featured || s.subagent || showOthers.value) && s.stats.length > 0
  )
)

const maxIndex = computed(() => Math.max(0, ...shownSeries.value.map((s) => s.stats.length - 1)))

const yMax = computed(() =>
  Math.max(1, ...shownSeries.value.map((s) => cumulativeOf(s.stats).at(-1) ?? 0))
)

function xFor(i: number): number {
  const innerW = width.value - margin.left - margin.right
  if (maxIndex.value === 0) return margin.left + innerW / 2
  return margin.left + (i / maxIndex.value) * innerW
}

function yFor(v: number): number {
  const innerH = height - margin.top - margin.bottom
  return margin.top + innerH - (v / yMax.value) * innerH
}

const attenuatedPalette = ['#5b6472', '#6d7688', '#83788f', '#6f8598']
const subagentPalette = ['#2fb5a0', '#4fb0d8', '#b08ad6', '#d8a04f']

const lines = computed(() => {
  let attIdx = 0
  let subIdx = 0
  return shownSeries.value.map((s) => {
    const cum = cumulativeOf(s.stats)
    const pts = cum.map((v, i) => `${xFor(i)},${yFor(v)}`).join(' ')
    return {
      id: s.session.id,
      title: (s.subagent ? '↳ ' : '') + (s.session.title || s.session.tag || s.session.id),
      featured: s.featured,
      total: cum.at(-1) ?? 0,
      color: s.featured
        ? 'var(--c-user)'
        : s.subagent
          ? subagentPalette[subIdx++ % subagentPalette.length]
          : attenuatedPalette[attIdx++ % attenuatedPalette.length],
      width: s.featured ? 2.4 : 1.2,
      opacity: s.featured ? 1 : s.subagent ? 0.85 : 0.5,
      dash: s.subagent && !s.featured ? '5 4' : undefined,
      points: pts,
    }
  })
})

const yTicks = computed(() => {
  const steps = 4
  return Array.from({ length: steps + 1 }, (_, i) => {
    const v = (yMax.value / steps) * i
    return { v, y: yFor(v) }
  })
})

// -- drag selection -----------------------------------------------------------
const drag = ref<{ active: boolean; start: number; cur: number }>({ active: false, start: 0, cur: 0 })

function svgX(ev: MouseEvent): number {
  const rect = (ev.currentTarget as SVGElement).getBoundingClientRect()
  const scale = width.value / rect.width
  const x = (ev.clientX - rect.left) * scale
  return Math.max(margin.left, Math.min(width.value - margin.right, x))
}

function nearestIndex(x: number): number {
  const stats = featured.value?.stats ?? []
  if (stats.length === 0) return 0
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < stats.length; i++) {
    const d = Math.abs(xFor(i) - x)
    if (d < bestD) {
      bestD = d
      best = i
    }
  }
  return best
}

function onDown(ev: MouseEvent) {
  const x = svgX(ev)
  drag.value = { active: true, start: x, cur: x }
}
function onMove(ev: MouseEvent) {
  if (!drag.value.active) return
  drag.value.cur = svgX(ev)
}
function onUp() {
  drag.value.active = false
}

const selection = computed(() => {
  const stats = featured.value?.stats ?? []
  if (stats.length === 0) return null
  const x0 = Math.min(drag.value.start, drag.value.cur)
  const x1 = Math.max(drag.value.start, drag.value.cur)
  if (x1 - x0 < 3) return null
  const i0 = nearestIndex(x0)
  const i1 = nearestIndex(x1)
  if (i1 < i0) return null
  const slice = stats.slice(i0, i1 + 1)
  const usage: Usage = slice.reduce(
    (acc, s) => ({
      input_tokens: acc.input_tokens + s.input_tokens,
      output_tokens: acc.output_tokens + s.output_tokens,
      cache_read_tokens: acc.cache_read_tokens + s.cache_read_tokens,
      cache_write_tokens: acc.cache_write_tokens + s.cache_write_tokens,
    }),
    { input_tokens: 0, output_tokens: 0, cache_read_tokens: 0, cache_write_tokens: 0 }
  )
  const tokens = slice.reduce((sum, s) => sum + consumed(s), 0)
  return {
    px0: xFor(i0),
    px1: xFor(i1),
    i0,
    i1,
    tokens,
    cost: estimateCost(usage, props.featuredModel),
  }
})

const hasData = computed(() => (featured.value?.stats.length ?? 0) > 0)
const hasOthers = computed(() =>
  props.series.some((s) => !s.featured && !s.subagent && s.stats.length > 0)
)
</script>

<template>
  <div ref="el" class="chart-wrap">
    <p v-if="!hasData" class="empty">
      No round trips: here you'll see the total tokens burned pile up round trip after round trip.
    </p>
    <template v-else>
      <div class="controls">
        <label v-if="hasOthers" class="toggle">
          <input v-model="showOthers" type="checkbox" />
          compare with other sessions
        </label>
        <span class="readout">
          <template v-if="selection">
            round trip {{ selection.i0 }}–{{ selection.i1 }}:
            <b>{{ formatTokens(selection.tokens) }}</b> tokens ·
            <b>{{ formatCost(selection.cost) }}</b>
          </template>
          <template v-else>drag over the chart to measure an interval</template>
        </span>
      </div>

      <svg
        :viewBox="`0 0 ${width} ${height}`"
        :height="height"
        width="100%"
        role="img"
        class="plot"
        @mousedown="onDown"
        @mousemove="onMove"
        @mouseup="onUp"
        @mouseleave="onUp"
      >
        <g class="axis">
          <template v-for="t in yTicks" :key="t.v">
            <line :x1="margin.left" :y1="t.y" :x2="width - margin.right" :y2="t.y" class="grid" />
            <text :x="margin.left - 8" :y="t.y + 3" class="tick" text-anchor="end">
              {{ formatTokens(t.v) }}
            </text>
          </template>
        </g>

        <rect
          v-if="selection"
          :x="selection.px0"
          :y="margin.top"
          :width="Math.max(1, selection.px1 - selection.px0)"
          :height="height - margin.top - margin.bottom"
          class="selection"
        />

        <polyline
          v-for="l in lines"
          :key="l.id"
          :points="l.points"
          fill="none"
          :stroke="l.color"
          :stroke-width="l.width"
          :opacity="l.opacity"
          :stroke-dasharray="l.dash"
          stroke-linejoin="round"
        />
      </svg>

      <div v-if="lines.length > 1" class="legend">
        <span v-for="l in lines" :key="'lg' + l.id" class="legend-item">
          <span class="swatch" :style="{ backgroundColor: l.color }"></span>
          {{ l.title }} · {{ formatTokens(l.total) }}
        </span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
  width: 100%;
}

.empty {
  color: var(--muted);
  font-style: italic;
  padding: 1.5rem 0;
}

.controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  font-size: 0.75rem;
  color: var(--muted);
  margin-bottom: 0.4rem;
}

.toggle {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  cursor: pointer;
}

.readout b {
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.plot {
  cursor: crosshair;
  user-select: none;
}

.grid {
  stroke: var(--border);
  stroke-width: 1;
}

.tick {
  fill: var(--muted);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.selection {
  fill: var(--c-user);
  fill-opacity: 0.14;
  stroke: var(--c-user);
  stroke-opacity: 0.5;
  stroke-width: 1;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1rem;
  margin-top: 0.35rem;
  font-size: 0.72rem;
  color: var(--muted);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-variant-numeric: tabular-nums;
}

.swatch {
  width: 14px;
  height: 3px;
  border-radius: 2px;
  display: inline-block;
}
</style>
