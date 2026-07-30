<script setup lang="ts">
/**
 * "What the context is made of" (featured): stacked area per round trip with
 * cache_read, the cache_write split by TTL (1h / 5m / tier not reported), new
 * input and output. The cache-write tiers are separate series because they cost
 * differently (2×input vs 1.25×input) and Claude Code mixes them across a
 * session. Hover: tooltip with the breakdown; click: navigate to the session
 * and select the event.
 */
import { computed, ref } from 'vue'
import type { StatsItem } from '../../types'
import { useElementWidth } from '../../composables/useElementSize'
import { cacheWriteTiers } from '../../utils/cache'
import { formatTokens } from '../../utils/format'

const props = defineProps<{
  stats: StatsItem[]
  sessionId: string | null
}>()

const emit = defineEmits<{ (e: 'jump', sessionId: string, eventId: number): void }>()

const LAYERS = [
  { key: 'cache_read', label: 'cache_read', color: '#4f9dff', value: (s: StatsItem) => s.cache_read_tokens },
  { key: 'cache_write_1h', label: 'cache_write 1h', color: '#7c5cf0', value: (s: StatsItem) => cacheWriteTiers(s).h1 },
  { key: 'cache_write_5m', label: 'cache_write 5m', color: '#c4b5fd', value: (s: StatsItem) => cacheWriteTiers(s).m5 },
  { key: 'cache_write_na', label: 'cache_write (TTL n/a)', color: '#8d8da6', value: (s: StatsItem) => cacheWriteTiers(s).unknown },
  { key: 'input', label: 'new input', color: '#3ecf6e', value: (s: StatsItem) => s.input_tokens },
  { key: 'output', label: 'output', color: '#f0883e', value: (s: StatsItem) => s.output_tokens },
] as const

const el = ref<HTMLElement | null>(null)
const width = useElementWidth(el, 680)
const height = 260
const margin = { top: 14, right: 16, bottom: 26, left: 52 }

function total(s: StatsItem): number {
  return LAYERS.reduce((sum, l) => sum + l.value(s), 0)
}

/** Layers with at least one non-zero point: keeps the legend and the tooltip
 *  free of the tiers this run never used (typically "TTL n/a"). */
const activeLayers = computed(() => LAYERS.filter((l) => props.stats.some((s) => l.value(s) > 0)))

const maxIndex = computed(() => Math.max(0, props.stats.length - 1))
const yMax = computed(() => Math.max(1, ...props.stats.map(total)))

function xFor(i: number): number {
  const innerW = width.value - margin.left - margin.right
  if (maxIndex.value === 0) return margin.left + innerW / 2
  return margin.left + (i / maxIndex.value) * innerW
}

function yFor(v: number): number {
  const innerH = height - margin.top - margin.bottom
  return margin.top + innerH - (v / yMax.value) * innerH
}

/** X columns with the cumulative bounds of the series. Single column -> two edges. */
interface Column {
  x: number
  bounds: number[] // 0 followed by the cumulative after each layer
}

const columns = computed<Column[]>(() => {
  const build = (i: number, x: number): Column => {
    const s = props.stats[i]
    const bounds = [0]
    let acc = 0
    for (const l of LAYERS) {
      acc += l.value(s)
      bounds.push(acc)
    }
    return { x, bounds }
  }
  if (props.stats.length === 1) {
    // Full-width flat band to make the single round trip visible.
    return [
      build(0, margin.left),
      build(0, width.value - margin.right),
    ]
  }
  return props.stats.map((_, i) => build(i, xFor(i)))
})

const areaPaths = computed(() =>
  LAYERS.map((layer, li) => {
    const cols = columns.value
    if (cols.length === 0) return { color: layer.color, d: '' }
    const top = cols.map((c) => `${c.x},${yFor(c.bounds[li + 1])}`)
    const bottom = cols
      .slice()
      .reverse()
      .map((c) => `${c.x},${yFor(c.bounds[li])}`)
    return { color: layer.color, d: `M${top.join(' L')} L${bottom.join(' L')} Z` }
  })
)

const yTicks = computed(() => {
  const steps = 4
  return Array.from({ length: steps + 1 }, (_, i) => {
    const v = (yMax.value / steps) * i
    return { v, y: yFor(v) }
  })
})

// -- hit areas + tooltip -----------------------------------------------------
interface Hit {
  x: number
  wLeft: number
  wRight: number
  item: StatsItem
}

const hits = computed<Hit[]>(() =>
  props.stats.map((item, i) => {
    const x = xFor(i)
    const prevX = i > 0 ? xFor(i - 1) : margin.left
    const nextX = i < maxIndex.value ? xFor(i + 1) : width.value - margin.right
    return { x, wLeft: (x - prevX) / 2, wRight: (nextX - x) / 2, item }
  })
)

const tooltip = ref<{ show: boolean; x: number; item: StatsItem | null }>({
  show: false,
  x: 0,
  item: null,
})

function onHover(h: Hit) {
  tooltip.value = { show: true, x: h.x, item: h.item }
}
function onLeave() {
  tooltip.value.show = false
}
function onClick(item: StatsItem) {
  if (props.sessionId) emit('jump', props.sessionId, item.event_id)
}

const hasData = computed(() => props.stats.length > 0)
</script>

<template>
  <div ref="el" class="chart-wrap">
    <p v-if="!hasData" class="empty">
      No round trips: here you'll see how much of the context is cold cache, new text, or output.
    </p>
    <template v-else>
      <div class="legend">
        <span v-for="l in activeLayers" :key="l.key" class="legend-item">
          <i class="swatch" :style="{ backgroundColor: l.color }"></i>{{ l.label }}
        </span>
      </div>

      <svg :viewBox="`0 0 ${width} ${height}`" :height="height" width="100%" role="img">
        <g class="axis">
          <template v-for="t in yTicks" :key="t.v">
            <line :x1="margin.left" :y1="t.y" :x2="width - margin.right" :y2="t.y" class="grid" />
            <text :x="margin.left - 8" :y="t.y + 3" class="tick" text-anchor="end">
              {{ formatTokens(t.v) }}
            </text>
          </template>
        </g>

        <path
          v-for="(a, i) in areaPaths"
          :key="i"
          :d="a.d"
          :fill="a.color"
          fill-opacity="0.72"
          stroke="none"
        />

        <rect
          v-for="(h, i) in hits"
          :key="'hit' + i"
          :x="h.x - h.wLeft"
          :y="margin.top"
          :width="Math.max(1, h.wLeft + h.wRight)"
          :height="height - margin.top - margin.bottom"
          fill="transparent"
          class="hit"
          @mouseenter="onHover(h)"
          @mouseleave="onLeave"
          @click="onClick(h.item)"
        />
      </svg>

      <div
        v-if="tooltip.show && tooltip.item"
        class="tooltip"
        :style="{ left: tooltip.x + 'px' }"
      >
        <strong>turn {{ tooltip.item.turn_index ?? '—' }}</strong>
        <span v-for="l in activeLayers" :key="l.key" class="row">
          <i class="swatch" :style="{ backgroundColor: l.color }"></i>
          {{ l.label }}: {{ formatTokens(l.value(tooltip.item)) }}
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

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.9rem;
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 0.4rem;
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
  flex: none;
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

.hit {
  cursor: pointer;
}

.hit:hover {
  fill: rgba(255, 255, 255, 0.04);
}

.tooltip {
  position: absolute;
  top: 8px;
  transform: translateX(-50%);
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 0.4rem 0.55rem;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: 0.72rem;
  color: var(--muted);
  pointer-events: none;
  white-space: nowrap;
  z-index: 5;
}

.tooltip strong {
  color: var(--text);
}

.tooltip .row {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-variant-numeric: tabular-nums;
}
</style>
