<script setup lang="ts">
/**
 * Charts dashboard: entry point for analyzing context consumption. Shows a
 * "featured" session (the live one if any, otherwise the most recent) with
 * metrics and SVG charts, its sub-agents, and at the bottom the session list
 * + quickstart. Real data only.
 */
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useSpyStore, type SessionNode } from '../stores/spy'
import { fetchSessionEvents } from '../api/client'
import { abbreviateModel } from '../utils/model'
import { tagColor } from '../utils/tag'
import type { EventSummary, Session } from '../types'
import MetricCards from '../components/dashboard/MetricCards.vue'
import ContextChart from '../components/dashboard/ContextChart.vue'
import CompositionChart from '../components/dashboard/CompositionChart.vue'
import CumulativeChart from '../components/dashboard/CumulativeChart.vue'
import SubagentBars from '../components/dashboard/SubagentBars.vue'
import ViewToggle from '../components/ViewToggle.vue'

const spy = useSpyStore()

const topLevelSessions = computed(() =>
  Object.values(spy.sessions)
    .filter((s) => !s.parent_session_id)
    .slice()
    .sort((a, b) => (b.started_at ?? 0) - (a.started_at ?? 0))
)

// -- parentage ---------------------------------------------------------------
const childrenMap = computed(() => {
  const byParent = new Map<string, Session[]>()
  for (const s of Object.values(spy.sessions)) {
    if (!s.parent_session_id) continue
    const bucket = byParent.get(s.parent_session_id)
    if (bucket) bucket.push(s)
    else byParent.set(s.parent_session_id, [s])
  }
  return byParent
})

/** (Recursive) descendants of a session, in visit order. */
function descendantsOf(id: string): Session[] {
  const out: Session[] = []
  const walk = (cur: string) => {
    for (const child of childrenMap.value.get(cur) ?? []) {
      out.push(child)
      walk(child.id)
    }
  }
  walk(id)
  return out
}

/** Top-level ancestor, walking up the parent chain. */
function rootAncestorOf(id: string): string {
  let cur = id
  let parent = spy.sessions[cur]?.parent_session_id ?? null
  while (parent) {
    cur = parent
    parent = spy.sessions[cur]?.parent_session_id ?? null
  }
  return cur
}

// -- featured session ----------------------------------------------------
// Lives in the store (featuredSessionId): so a sidebar click while already on
// the dashboard can change it without navigating, and it survives route
// changes. It can also be a sub-agent: the charts then show ITS round trips.
const { featuredSessionId: featuredId } = storeToRefs(spy)

watch(
  () => spy.sessions,
  (all) => {
    if (featuredId.value && all[featuredId.value]) return
    const list = topLevelSessions.value
    const live = list.find((s) => s.live)
    featuredId.value = (live ?? list[0])?.id ?? null
  },
  { immediate: true, deep: false }
)

const featured = computed<Session | null>(() =>
  featuredId.value ? (spy.sessions[featuredId.value] ?? null) : null
)

/** The featured session is a sub-agent (has a parent): the charts show ITS work. */
const featuredIsSub = computed(() => !!featured.value?.parent_session_id)

/** Fallback name (short id) when the session carries neither tag nor title. */
const featuredFallbackName = computed(() => {
  const s = featured.value
  if (!s || s.tag || s.title) return null
  return s.id.length > 12 ? `${s.id.slice(0, 12)}…` : s.id
})

/** Options for the featured-session select: flattened tree, sub-agents indented. */
const sessionOptions = computed(() => {
  const out: { id: string; label: string }[] = []
  const walk = (nodes: SessionNode[], depth: number) => {
    for (const n of nodes) {
      const name = n.title || n.tag || n.id
      const indent = '  '.repeat(depth)
      out.push({
        id: n.id,
        label: `${indent}${depth > 0 ? '└ ' : ''}${name}${n.live ? ' · live' : ''}`,
      })
      walk(n.children, depth + 1)
    }
  }
  walk(spy.sessionTree, 0)
  return out
})

// -- loading stats for all sessions (refreshed for live ones) --------
// Sub-agents too: they have their own round trips and can be featured.
const loadedRoundTrips = new Map<string, number>()

watch(
  () => Object.values(spy.sessions),
  (list) => {
    for (const s of list) {
      const prev = loadedRoundTrips.get(s.id)
      if (prev === undefined || prev !== s.round_trips) {
        loadedRoundTrips.set(s.id, s.round_trips)
        void spy.loadStatsFor(s.id, prev !== undefined)
      }
    }
  },
  { immediate: true, deep: true }
)

/**
 * Chart series: the top-level sessions plus the descendants of the featured
 * family (dashed), so sub-agent work is visible next to the orchestrator's.
 */
const series = computed(() => {
  const out = topLevelSessions.value.map((s) => ({
    session: s,
    stats: spy.statsBySession[s.id] ?? [],
    featured: s.id === featuredId.value,
    subagent: false,
  }))
  if (featuredId.value) {
    for (const d of descendantsOf(rootAncestorOf(featuredId.value))) {
      out.push({
        session: d,
        stats: spy.statsBySession[d.id] ?? [],
        featured: d.id === featuredId.value,
        subagent: true,
      })
    }
  }
  return out
})

const featuredStats = computed(() =>
  featuredId.value ? (spy.statsBySession[featuredId.value] ?? []) : []
)

// -- featured session's events: user prompt (hook UserPromptSubmit) ------------
const featuredEvents = ref<EventSummary[]>([])
let eventsToken = 0

watch(
  () => (featured.value ? `${featured.value.id}:${featured.value.round_trips}` : null),
  async (key) => {
    if (!featured.value || !key) {
      featuredEvents.value = []
      return
    }
    const token = ++eventsToken
    try {
      const evts = await fetchSessionEvents(featured.value.id)
      if (token === eventsToken) featuredEvents.value = evts
    } catch {
      if (token === eventsToken) featuredEvents.value = []
    }
  },
  { immediate: true }
)

const userPromptEvents = computed(() =>
  featuredEvents.value.filter((e) => e.kind === 'hook' && e.subkind === 'UserPromptSubmit')
)

const promptCount = computed(() => userPromptEvents.value.length)

const userPromptTurns = computed(() => {
  const set = new Set<number>()
  for (const e of userPromptEvents.value) {
    if (e.turn_index != null) set.add(e.turn_index)
  }
  return set
})

// -- sub-agents (descendants of the featured session) ----------------------------------
const subagents = computed<Session[]>(() =>
  featuredId.value ? descendantsOf(featuredId.value) : []
)

// -- navigation -------------------------------------------------------------
/** Click on a sub-agent bar: features it (the charts become its own). */
const rootEl = ref<HTMLElement | null>(null)
function featureSession(id: string) {
  featuredId.value = id
  // scrolling happens on main.center, not window: scroll up via the root
  rootEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/**
 * Click on a chart point: open the event detail in the right panel *in place*,
 * without leaving the charts (the detail sidebar would otherwise never show
 * here). Also feature the clicked session so the charts follow it.
 */
function jumpToEvent(sessionId: string, eventId: number) {
  featuredId.value = sessionId
  void spy.select(eventId)
}

// -- scroll to sub-agents from the metric card -------------------------------------
const subagentPanel = ref<HTMLElement | null>(null)
function scrollToSubagents() {
  subagentPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

</script>

<template>
  <div ref="rootEl" class="dashboard">
    <header class="header">
      <div class="title-block">
        <h1>agentspy</h1>
        <p class="subtitle">
          Come Claude Code riempie il contesto: token in gioco, composizione e consumo cumulativo.
        </p>
      </div>
      <div class="header-right">
        <ViewToggle />
        <label v-if="topLevelSessions.length" class="featured-select">
          <span>featured session</span>
          <select v-model="featuredId">
            <option v-for="o in sessionOptions" :key="o.id" :value="o.id">{{ o.label }}</option>
          </select>
        </label>
      </div>
    </header>

    <p v-if="topLevelSessions.length === 0" class="empty-hero">
      No sessions yet. Start the server and a Claude Code session (see the “?” help at the
      bottom-left) to populate the dashboard.
    </p>

    <template v-else>
      <!-- Identity of the session the charts are about: the one thing that must
           change when you switch session (via sidebar or select). The tag chip
           reuses the sidebar's colour hash, tying "that row → these charts". -->
      <div v-if="featured" class="featured-identity">
        <span class="fi-label">grafici della sessione</span>
        <span
          v-if="featured.tag"
          class="fi-chip"
          :style="{ backgroundColor: tagColor(featured.tag) }"
        >
          {{ featured.tag }}
        </span>
        <span v-if="featured.title" class="fi-title">{{ featured.title }}</span>
        <span v-else-if="featuredFallbackName" class="fi-title">{{ featuredFallbackName }}</span>
        <span v-if="featuredIsSub" class="fi-badge fi-badge--sub">sub-agent</span>
        <span class="fi-meta">{{ abbreviateModel(featured.model) }}</span>
        <span class="fi-meta">· {{ featured.round_trips }} round trips</span>
        <span v-if="featured.live" class="fi-badge fi-badge--live">live</span>
      </div>

      <MetricCards
        :stats="featuredStats"
        :model="featured?.model ?? null"
        :prompt-count="promptCount"
        :subagents="subagents"
        @jump-subagents="scrollToSubagents"
      />

      <section class="panel">
        <div class="panel-head">
          <h2>Context per round trip</h2>
          <p class="panel-sub">
            How many tokens travel on each call. Each line is a session (dashed = a sub-agent
            belonging to the featured family); the green markers are round trips opened by one of
            your prompts. The red line is the featured model's context window (200k or 1M).
          </p>
        </div>
        <ContextChart :series="series" :user-prompt-turns="userPromptTurns" @jump="jumpToEvent" />
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>What the context is made of</h2>
          <p class="panel-sub">
            The same spend broken down: cache re-read (cold), cache written, new text and output.
            Cache is what makes long round trips sustainable.
          </p>
        </div>
        <CompositionChart :stats="featuredStats" :session-id="featuredId" @jump="jumpToEvent" />
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Cumulative consumption (integral)</h2>
          <p class="panel-sub">
            The accumulating total burned: this — not the peak — is what determines the cost. Drag
            to measure how much a stretch of the conversation cost.
          </p>
        </div>
        <CumulativeChart :series="series" :featured-model="featured?.model ?? null" />
      </section>

      <section v-if="subagents.length" ref="subagentPanel" class="panel">
        <div class="panel-head">
          <h2>Sub-agents</h2>
          <p class="panel-sub">
            Sub-agents work on a separate context: here are each one's total tokens, to see where
            spending hidden from the main thread goes. Click a bar to feature that sub-agent and see
            its charts.
          </p>
        </div>
        <SubagentBars :subagents="subagents" @open="featureSession" />
      </section>
    </template>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 1.5rem 2rem 3rem;
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

h1 {
  font-size: 1.7rem;
  margin-bottom: 0.2rem;
}

.subtitle {
  color: var(--muted);
  font-size: 0.9rem;
  max-width: 60ch;
}

.header-right {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.featured-select {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.72rem;
  color: var(--muted);
}

.featured-select select {
  background-color: var(--panel-alt);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 0.35rem 0.5rem;
  font-size: 0.85rem;
  min-width: 220px;
}

.empty-hero {
  color: var(--muted);
  padding: 2rem 0;
}

/* Session identity: the heading that actually changes on session switch.
   Sits above the metric cards, where the eye lands after the header. */
.featured-identity {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.55rem 0.75rem;
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent-live);
  border-radius: 8px;
}

.fi-label {
  font: 700 0.62rem system-ui;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted-faint);
}

.fi-chip {
  padding: 0.1rem 0.5rem;
  border-radius: 99px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #fff;
}

.fi-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text);
}

.fi-meta {
  font-size: 0.78rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.fi-badge {
  padding: 0.05rem 0.4rem;
  border-radius: 99px;
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.fi-badge--live {
  background-color: var(--accent-live);
  color: #fff;
}

.fi-badge--sub {
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  color: var(--muted);
}

/* Chart panels render on a dark "focus" card regardless of the app theme, to
   match the reference design (Image 10): the coloured series pop against dark
   and the panels read as a distinct analytical surface. Re-declaring the
   palette tokens here makes the SVG chart internals (grid, ticks, text,
   legends) — which all reference these vars — adapt without touching each
   chart component. */
.panel {
  --bg: #0e1218;
  --panel: #12171f;
  --panel-alt: #1a212b;
  --border: #232a36;
  --text: #e7e9ee;
  --muted: #9aa4b2;
  --muted-faint: #6b7480;
  --accent: #a78bfa;
  background-color: #0e1218;
  border: 1px solid #232a36;
  border-radius: 8px;
  padding: 1rem 1.25rem 1.1rem;
  color: var(--text);
}

.panel-head {
  margin-bottom: 0.6rem;
}

.panel-head h2 {
  font-size: 1rem;
  margin-bottom: 0.15rem;
}

.panel-sub {
  color: var(--muted);
  font-size: 0.78rem;
  max-width: 70ch;
}

</style>
