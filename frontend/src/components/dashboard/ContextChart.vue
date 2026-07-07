<script setup lang="ts">
/**
 * "Contesto per round trip": una polyline per sessione top-level. Y = token in
 * contesto (input + cache_read + cache_write), X = indice round trip. La
 * featured è in accent e più spessa, le altre attenuate. Marker verdi sui
 * round trip innescati da un prompt utente (solo featured). Click su un punto:
 * naviga alla sessione e seleziona l'evento.
 */
import { computed, ref } from 'vue'
import type { Session, StatsItem } from '../../types'
import { useElementWidth } from '../../composables/useElementSize'
import { formatTokens } from '../../utils/format'

interface Series {
  session: Session
  stats: StatsItem[]
  featured: boolean
}

const props = defineProps<{
  series: Series[]
  /** turn_index dei round trip innescati da un prompt utente (featured). */
  userPromptTurns: Set<number>
}>()

const emit = defineEmits<{ (e: 'jump', sessionId: string, eventId: number): void }>()

const CONTEXT_LIMIT = 200_000
const LIMIT_VISIBLE_THRESHOLD = 80_000

const el = ref<HTMLElement | null>(null)
const width = useElementWidth(el, 680)
const height = 280
const margin = { top: 14, right: 16, bottom: 26, left: 52 }

const attenuatedPalette = ['#5b6472', '#6d7688', '#83788f', '#6f8598']

function contextTokens(s: StatsItem): number {
  return s.input_tokens + s.cache_read_tokens + s.cache_write_tokens
}

const maxIndex = computed(() =>
  Math.max(0, ...props.series.map((s) => s.stats.length - 1))
)

const maxReal = computed(() =>
  Math.max(1, ...props.series.flatMap((s) => s.stats.map(contextTokens)))
)

const showLimit = computed(() => maxReal.value > LIMIT_VISIBLE_THRESHOLD)

const yMax = computed(() =>
  showLimit.value ? Math.max(maxReal.value, CONTEXT_LIMIT) : maxReal.value
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

interface Point {
  x: number
  y: number
  tokens: number
  turn: number | null
  eventId: number
  idx: number
}

interface SeriesView {
  id: string
  title: string
  featured: boolean
  color: string
  strokeWidth: number
  opacity: number
  polyline: string
  points: Point[]
}

const seriesViews = computed<SeriesView[]>(() => {
  let attIdx = 0
  const views = props.series.map((s): SeriesView => {
    const featured = s.featured
    const color = featured ? 'var(--accent)' : attenuatedPalette[attIdx++ % attenuatedPalette.length]
    const points: Point[] = s.stats.map((item, idx) => ({
      x: xFor(idx),
      y: yFor(contextTokens(item)),
      tokens: contextTokens(item),
      turn: item.turn_index,
      eventId: item.event_id,
      idx,
    }))
    return {
      id: s.session.id,
      title: s.session.title || s.session.tag || s.session.id,
      featured,
      color,
      strokeWidth: featured ? 2.4 : 1.2,
      opacity: featured ? 1 : 0.55,
      polyline: points.map((p) => `${p.x},${p.y}`).join(' '),
      points,
    }
  })
  // featured disegnata per ultima (sopra le altre)
  return views.sort((a, b) => Number(a.featured) - Number(b.featured))
})

/** Marker verticali dei prompt utente: primo round trip di ogni turno-prompt della featured. */
const promptMarkers = computed<number[]>(() => {
  const featured = props.series.find((s) => s.featured)
  if (!featured) return []
  const seenTurns = new Set<number>()
  const xs: number[] = []
  featured.stats.forEach((item, idx) => {
    const t = item.turn_index
    if (t != null && props.userPromptTurns.has(t) && !seenTurns.has(t)) {
      seenTurns.add(t)
      xs.push(xFor(idx))
    }
  })
  return xs
})

const yTicks = computed(() => {
  const steps = 4
  return Array.from({ length: steps + 1 }, (_, i) => {
    const v = (yMax.value / steps) * i
    return { v, y: yFor(v) }
  })
})

const limitY = computed(() => yFor(CONTEXT_LIMIT))

// -- tooltip -----------------------------------------------------------------
const tooltip = ref<{ show: boolean; x: number; y: number; title: string; turn: number | null; tokens: number }>(
  { show: false, x: 0, y: 0, title: '', turn: null, tokens: 0 }
)

function onHover(view: SeriesView, p: Point) {
  tooltip.value = {
    show: true,
    x: p.x,
    y: p.y,
    title: view.title,
    turn: p.turn,
    tokens: p.tokens,
  }
}

function onLeave() {
  tooltip.value.show = false
}

const hasData = computed(() => props.series.some((s) => s.stats.length > 0))
</script>

<template>
  <div ref="el" class="chart-wrap">
    <p v-if="!hasData" class="empty">
      Nessun round trip da mostrare: apri o avvia una sessione per vedere come cresce il contesto.
    </p>
    <template v-else>
      <svg :viewBox="`0 0 ${width} ${height}`" :height="height" width="100%" role="img">
        <!-- griglia + etichette Y -->
        <g class="axis">
          <template v-for="t in yTicks" :key="t.v">
            <line :x1="margin.left" :y1="t.y" :x2="width - margin.right" :y2="t.y" class="grid" />
            <text :x="margin.left - 8" :y="t.y + 3" class="tick" text-anchor="end">
              {{ formatTokens(t.v) }}
            </text>
          </template>
        </g>

        <!-- linea limite 200k -->
        <g v-if="showLimit">
          <line
            :x1="margin.left"
            :y1="limitY"
            :x2="width - margin.right"
            :y2="limitY"
            class="limit-line"
          />
          <text :x="width - margin.right" :y="limitY - 5" class="limit-label" text-anchor="end">
            limite 200k
          </text>
        </g>

        <!-- marker prompt utente -->
        <line
          v-for="(x, i) in promptMarkers"
          :key="'pm' + i"
          :x1="x"
          :y1="margin.top"
          :x2="x"
          :y2="height - margin.bottom"
          class="prompt-marker"
        />

        <!-- polyline per sessione -->
        <polyline
          v-for="v in seriesViews"
          :key="v.id"
          :points="v.polyline"
          fill="none"
          :stroke="v.color"
          :stroke-width="v.strokeWidth"
          :opacity="v.opacity"
          stroke-linejoin="round"
        />

        <!-- punti interattivi -->
        <template v-for="v in seriesViews" :key="'pts' + v.id">
          <circle
            v-for="p in v.points"
            :key="v.id + '-' + p.idx"
            :cx="p.x"
            :cy="p.y"
            :r="v.featured ? 3.2 : 2.2"
            :fill="v.color"
            :opacity="v.opacity"
            class="point"
            @mouseenter="onHover(v, p)"
            @mouseleave="onLeave"
            @click="emit('jump', v.id, p.eventId)"
          />
        </template>
      </svg>

      <div
        v-if="tooltip.show"
        class="tooltip"
        :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
      >
        <strong>{{ tooltip.title }}</strong>
        <span>turno {{ tooltip.turn ?? '—' }}</span>
        <span>{{ formatTokens(tooltip.tokens) }} token in contesto</span>
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

.grid {
  stroke: var(--border);
  stroke-width: 1;
}

.tick {
  fill: var(--muted);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.limit-line {
  stroke: var(--danger);
  stroke-width: 1.2;
  stroke-dasharray: 5 4;
  opacity: 0.85;
}

.limit-label {
  fill: var(--danger);
  font-size: 10px;
  opacity: 0.9;
}

.prompt-marker {
  stroke: var(--accent-live);
  stroke-width: 1;
  stroke-dasharray: 2 3;
  opacity: 0.55;
}

.point {
  cursor: pointer;
}

.point:hover {
  stroke: var(--text);
  stroke-width: 1.5;
}

.tooltip {
  position: absolute;
  transform: translate(-50%, calc(-100% - 10px));
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 0.4rem 0.55rem;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  font-size: 0.72rem;
  color: var(--muted);
  pointer-events: none;
  white-space: nowrap;
  z-index: 5;
}

.tooltip strong {
  color: var(--text);
}
</style>
