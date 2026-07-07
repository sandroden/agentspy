<script setup lang="ts">
/**
 * Dashboard grafica: punto d'ingresso per l'analisi del consumo di contesto.
 * Mostra una sessione "in evidenza" (featured: la live se esiste, altrimenti la
 * più recente) con metriche e grafici SVG, i subagenti, e in fondo l'elenco
 * sessioni + il quickstart. Solo dati reali.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useSpyStore, type SessionNode } from '../stores/spy'
import { fetchSessionEvents } from '../api/client'
import type { EventSummary, Session } from '../types'
import { formatDuration, formatTokens } from '../utils/format'
import MetricCards from '../components/dashboard/MetricCards.vue'
import ContextChart from '../components/dashboard/ContextChart.vue'
import CompositionChart from '../components/dashboard/CompositionChart.vue'
import CumulativeChart from '../components/dashboard/CumulativeChart.vue'
import SubagentBars from '../components/dashboard/SubagentBars.vue'

const spy = useSpyStore()
const router = useRouter()

const topLevelSessions = computed(() =>
  Object.values(spy.sessions)
    .filter((s) => !s.parent_session_id)
    .slice()
    .sort((a, b) => (b.started_at ?? 0) - (a.started_at ?? 0))
)

// -- parentele ---------------------------------------------------------------
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

/** Discendenti (ricorsivi) di una sessione, in ordine di visita. */
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

/** Capostipite top-level risalendo la catena dei parent. */
function rootAncestorOf(id: string): string {
  let cur = id
  let parent = spy.sessions[cur]?.parent_session_id ?? null
  while (parent) {
    cur = parent
    parent = spy.sessions[cur]?.parent_session_id ?? null
  }
  return cur
}

// -- sessione in evidenza ----------------------------------------------------
// Vive nello store (featuredSessionId): così il click in sidebar mentre si è
// già in dashboard può cambiarla senza navigare, e sopravvive ai cambi route.
// Può essere anche un subagente: i grafici mostrano i SUOI round trip.
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

/** Opzioni del select in evidenza: albero appiattito, subagenti indentati. */
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

// -- caricamento stats per tutte le sessioni (con refresh sulle live) --------
// Anche i subagenti: hanno round trip propri e possono essere featured.
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
 * Serie dei grafici: le top-level più i discendenti della famiglia in
 * evidenza (tratteggiati), così il lavoro dei subagenti è visibile accanto
 * a quello dell'orchestratore.
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

// -- eventi della featured: prompt utente (hook UserPromptSubmit) ------------
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

// -- subagenti (discendenti della featured) ----------------------------------
const subagents = computed<Session[]>(() =>
  featuredId.value ? descendantsOf(featuredId.value) : []
)

// -- navigazione -------------------------------------------------------------
function openSession(id: string) {
  void router.push(`/session/${id}`)
}

/** Click su una barra subagente: lo mette in evidenza (i grafici diventano i suoi). */
const rootEl = ref<HTMLElement | null>(null)
function featureSession(id: string) {
  featuredId.value = id
  // lo scroll avviene su main.center, non su window: si risale col root
  rootEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function jumpToEvent(sessionId: string, eventId: number) {
  void router.push(`/session/${sessionId}`)
  void spy.select(eventId)
}

// -- scroll ai subagenti dal metric card -------------------------------------
const subagentPanel = ref<HTMLElement | null>(null)
function scrollToSubagents() {
  subagentPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function totalTokens(s: Session): number {
  const u = s.usage_incl_children
  return u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
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
      <label v-if="topLevelSessions.length" class="featured-select">
        <span>sessione in evidenza</span>
        <select v-model="featuredId">
          <option v-for="o in sessionOptions" :key="o.id" :value="o.id">{{ o.label }}</option>
        </select>
      </label>
    </header>

    <p v-if="topLevelSessions.length === 0" class="empty-hero">
      Nessuna sessione ancora. Avvia il server e una sessione Claude Code (vedi Avvio rapido in
      fondo) per popolare la dashboard.
    </p>

    <template v-else>
      <MetricCards
        :stats="featuredStats"
        :model="featured?.model ?? null"
        :prompt-count="promptCount"
        :subagents="subagents"
        @jump-subagents="scrollToSubagents"
      />

      <section class="panel">
        <div class="panel-head">
          <h2>Contesto per round trip</h2>
          <p class="panel-sub">
            Quanti token viaggiano a ogni chiamata. Ogni linea è una sessione (tratteggiata = un
            subagente della famiglia in evidenza); i marker verdi sono i round trip aperti da un tuo
            prompt. La linea rossa è il tetto pratico di ~200k.
          </p>
        </div>
        <ContextChart :series="series" :user-prompt-turns="userPromptTurns" @jump="jumpToEvent" />
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Di cosa è fatto il contesto</h2>
          <p class="panel-sub">
            La stessa spesa scomposta: cache riletta (fredda), cache scritta, testo nuovo e output.
            La cache è ciò che rende sostenibili i round trip lunghi.
          </p>
        </div>
        <CompositionChart :stats="featuredStats" :session-id="featuredId" @jump="jumpToEvent" />
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Consumo cumulativo (integrale)</h2>
          <p class="panel-sub">
            Il totale bruciato che si accumula: è questo, non il picco, a determinare il costo.
            Trascina per misurare quanto è costato un tratto di conversazione.
          </p>
        </div>
        <CumulativeChart :series="series" :featured-model="featured?.model ?? null" />
      </section>

      <section v-if="subagents.length" ref="subagentPanel" class="panel">
        <div class="panel-head">
          <h2>Subagenti</h2>
          <p class="panel-sub">
            I subagenti lavorano su un contesto separato: qui i token totali di ciascuno, per capire
            dove va la spesa nascosta al thread principale. Click su una barra per mettere in
            evidenza il subagente e vederne i grafici.
          </p>
        </div>
        <SubagentBars :subagents="subagents" @open="featureSession" />
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Tutte le sessioni</h2>
        </div>
        <div class="cards">
          <div
            v-for="s in topLevelSessions"
            :key="s.id"
            class="card"
            :class="{ featured: s.id === featuredId }"
            @click="openSession(s.id)"
          >
            <div class="card-header">
              <span class="dot" :class="{ live: s.live }"></span>
              <strong>{{ s.title || s.id }}</strong>
            </div>
            <div class="card-meta">
              <span v-if="s.tag" class="chip">{{ s.tag }}</span>
              <span>{{ s.model }}</span>
              <span>{{ formatDuration(s.duration_s) }}</span>
              <span>{{ formatTokens(totalTokens(s)) }} tok</span>
            </div>
          </div>
        </div>
      </section>
    </template>

    <details class="quickstart">
      <summary>Avvio rapido</summary>
      <ol>
        <li><code>cd server && uv run agentspy</code></li>
        <li><code>ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude</code></li>
        <li>
          Per taggare una raccolta (separare run diverse):
          <code>ANTHROPIC_CUSTOM_HEADERS="x-agentspy-tag: mio-tag" claude</code>
        </li>
      </ol>
    </details>
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

.panel {
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem 1.25rem 1.1rem;
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

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.75rem;
}

.card {
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.75rem;
  cursor: pointer;
}

.card:hover {
  border-color: var(--accent);
}

.card.featured {
  border-color: var(--accent);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.4rem;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--muted);
}

.dot.live {
  background-color: var(--accent-live);
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: var(--muted);
}

.chip {
  background-color: var(--panel);
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  color: var(--text);
}

.quickstart {
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem 1.25rem;
}

.quickstart summary {
  cursor: pointer;
  color: var(--text);
  font-weight: 600;
}

.quickstart ol {
  padding-left: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.6rem;
}

code {
  background-color: var(--panel-alt);
  padding: 0.15rem 0.4rem;
  border-radius: 3px;
  font-size: 0.85rem;
}
</style>
