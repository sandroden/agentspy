<script setup lang="ts">
// Timeline verticale (tempo dall'alto verso il basso), raggruppata per
// turn_index. Legge SOLO spy.visibleEvents (già filtrato da live/pausa/
// cursore) + spy.sessions (per individuare i subagenti figli) e spy.detailCache
// (best-effort, per arricchire l'header di turno col prompt reale quando è
// già stato caricato da un click precedente).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useSpyStore } from '../stores/spy'
import type { EventSummary, Session } from '../types'
import TurnGroup from './timeline/TurnGroup.vue'

export interface SubagentRowData {
  agentId: string
  childId: string | null
  ts: number
  label: string
}

export type TimelineRow =
  | { rowKind: 'event'; event: EventSummary; nextRt?: EventSummary }
  | { rowKind: 'subagent'; data: SubagentRowData }
  | { rowKind: 'gap'; seconds: number }

export interface TimelineGroup {
  key: string
  turnIndex: number | null
  startTs: number | null
  promptSnippet: string
  rows: TimelineRow[]
  roundTrips: number
  outputTokens: number
  durationS: number | null
}

const spy = useSpyStore()

const GAP_SECONDS = 30

/**
 * Raggruppa spy.visibleEvents per turno in un solo passaggio O(n), evitando
 * lavoro ripetuto nel template. I subagenti sono individuati in due modi
 * (vedi PLAN.md/correlate.py): (a) un evento della sessione corrente porta
 * già un `agent_id` (schema hook non ancora verificato empiricamente per il
 * SubagentStart lato genitore); (b) esiste una sessione figlia
 * (parent_session_id === sessione corrente) il cui agent_id non compare in
 * nessun evento — in tal caso viene inserita come marker temporale in base a
 * `started_at`. In entrambi i casi si mostra solo un blocco di rimando, mai
 * gli eventi del figlio.
 */
const groups = computed<TimelineGroup[]>(() => {
  // nota: i PostToolUse sono già filtrati alla fonte (stores/spy.ts)
  const evts = spy.visibleEvents
  const parentId = spy.currentSessionId
  // l'agent_id della sessione APERTA (se essa stessa è un subagente): un
  // evento che lo riporta è solo l'eco del proprio stato di correlazione
  // (es. SubagentStart/Stop nella sessione figlia stessa), non un nipote.
  const ownAgentId = spy.currentSession?.agent_id ?? null
  const children: Session[] = parentId
    ? Object.values(spy.sessions).filter((s) => s.parent_session_id === parentId && s.agent_id)
    : []
  const claimedAgentIds = new Set(
    evts
      .filter((e): e is EventSummary & { agent_id: string } => !!e.agent_id && e.agent_id !== ownAgentId)
      .map((e) => e.agent_id)
  )
  // in pausa (o con cursore indietro) `evts` copre solo il tempo fino al
  // cursore: un figlio nato dopo quell'istante non deve ancora comparire,
  // altrimenti la timeline "anticipa" eventi rispetto al cursore.
  const maxVisibleTs = evts.reduce(
    (max, e) => Math.max(max, (e.ts_start ?? 0) + (e.duration_s ?? 0)),
    -Infinity
  )
  const unclaimedChildren = children.filter(
    (c) => !claimedAgentIds.has(c.agent_id as string) && (c.started_at ?? Infinity) <= maxVisibleTs
  )

  type Anchor =
    | { ts: number; anchorKind: 'event'; event: EventSummary }
    | { ts: number; anchorKind: 'subagent'; child: Session }

  const anchors: Anchor[] = [
    ...evts.map((event): Anchor => ({ ts: event.ts_start ?? 0, anchorKind: 'event', event })),
    ...unclaimedChildren.map((child): Anchor => ({ ts: child.started_at ?? 0, anchorKind: 'subagent', child })),
  ]
  anchors.sort((a, b) => a.ts - b.ts)

  const byKey = new Map<string, TimelineGroup>()
  const order: string[] = []
  let currentTurn: number | null = null
  let lastAgentId: string | null = null
  let lastEndTs: number | null = null

  function ensureGroup(turnIndex: number | null, ts: number): TimelineGroup {
    const key = turnIndex === null ? 'none' : String(turnIndex)
    let g = byKey.get(key)
    if (!g) {
      g = {
        key,
        turnIndex,
        startTs: ts,
        promptSnippet: '',
        rows: [],
        roundTrips: 0,
        outputTokens: 0,
        durationS: null,
      }
      byKey.set(key, g)
      order.push(key)
    }
    return g
  }

  for (const anchor of anchors) {
    if (anchor.anchorKind === 'event') currentTurn = anchor.event.turn_index ?? currentTurn
    const turnIndex = anchor.anchorKind === 'event' ? (anchor.event.turn_index ?? currentTurn) : currentTurn
    const group = ensureGroup(turnIndex, anchor.ts)

    if (lastEndTs != null && anchor.ts - lastEndTs > GAP_SECONDS) {
      group.rows.push({ rowKind: 'gap', seconds: anchor.ts - lastEndTs })
    }

    if (anchor.anchorKind === 'subagent') {
      const c = anchor.child
      group.rows.push({
        rowKind: 'subagent',
        data: { agentId: c.agent_id as string, childId: c.id, ts: anchor.ts, label: c.title || (c.agent_id as string) },
      })
      lastEndTs = c.ended_at ?? anchor.ts
      lastAgentId = null
      continue
    }

    const e = anchor.event
    const rowEnd = (e.ts_start ?? 0) + (e.duration_s ?? 0)

    if (e.agent_id && e.agent_id !== ownAgentId) {
      if (lastAgentId === e.agent_id) {
        // estende il blocco subagente già aperto: nessuna nuova riga
        lastEndTs = rowEnd
        continue
      }
      const child = children.find((c) => c.agent_id === e.agent_id) ?? null
      group.rows.push({
        rowKind: 'subagent',
        data: { agentId: e.agent_id, childId: child?.id ?? null, ts: e.ts_start ?? 0, label: child?.title || e.agent_id },
      })
      lastAgentId = e.agent_id
      lastEndTs = rowEnd
      continue
    }

    lastAgentId = null
    group.rows.push({ rowKind: 'event', event: e })
    lastEndTs = rowEnd
    if (e.kind === 'round_trip') {
      group.roundTrips++
      group.outputTokens += e.usage.output_tokens
    }
    if (e.kind === 'hook' && e.subkind === 'UserPromptSubmit' && !group.promptSnippet) {
      const cached = spy.detailCache[e.id]
      const payload = cached?.payload as Record<string, unknown> | undefined
      const prompt = payload && typeof payload.prompt === 'string' ? payload.prompt : ''
      if (prompt) group.promptSnippet = prompt.slice(0, 160)
    }
  }

  // Gauge di contesto DOPO ogni tool_use: il contesto "dopo" è esattamente
  // l'input del round trip successivo (la richiesta che contiene il
  // tool_result), quindi ogni marker tool_use eredita usage/model di quel
  // round trip. Scansione all'indietro: nextRt = round trip più vicino che segue.
  {
    const eventRows = order
      .flatMap((k) => (byKey.get(k) as TimelineGroup).rows)
      .filter((r): r is TimelineRow & { rowKind: 'event' } => r.rowKind === 'event')
    let nextRt: EventSummary | undefined
    for (let i = eventRows.length - 1; i >= 0; i--) {
      const r = eventRows[i]
      if (r.event.kind === 'round_trip') nextRt = r.event
      else if (r.event.kind === 'hook' && r.event.subkind === 'PreToolUse') r.nextRt = nextRt
    }
  }

  for (const key of order) {
    const g = byKey.get(key) as TimelineGroup
    if (!g.promptSnippet) {
      const firstRoundTrip = g.rows.find(
        (r): r is TimelineRow & { rowKind: 'event' } => r.rowKind === 'event' && r.event.kind === 'round_trip'
      )
      if (firstRoundTrip) g.promptSnippet = firstRoundTrip.event.snippet
    }
    const timestamps = g.rows
      .map((r) => (r.rowKind === 'event' ? r.event.ts_start : r.rowKind === 'subagent' ? r.data.ts : null))
      .filter((v): v is number => v != null)
    if (timestamps.length) {
      g.startTs = Math.min(...timestamps)
      g.durationS = Math.max(...timestamps) - g.startTs
    }
  }

  return order.map((k) => byKey.get(k) as TimelineGroup)
})

// -- scroll "segui" -----------------------------------------------------
const rootEl = ref<HTMLElement | null>(null)
const showFollowButton = ref(false)
let scrollContainer: HTMLElement | null = null
let stickToBottom = true
const NEAR_BOTTOM_PX = 150

function findScrollContainer(el: HTMLElement | null): HTMLElement {
  // Basato solo sullo stile (non su scrollHeight > clientHeight): a
  // onMounted il contenuto reale non è ancora arrivato (fetch async), quindi
  // `.center` potrebbe non "traboccare" ancora pur essendo il vero
  // contenitore di scroll — verificarlo via overflow-y è stabile a
  // prescindere dal contenuto già caricato.
  let node = el?.parentElement ?? null
  while (node) {
    const style = getComputedStyle(node)
    if (/(auto|scroll)/.test(style.overflowY)) return node
    node = node.parentElement
  }
  return (document.scrollingElement as HTMLElement) ?? document.documentElement
}

function isNearBottom(): boolean {
  if (!scrollContainer) return true
  return scrollContainer.scrollHeight - scrollContainer.scrollTop - scrollContainer.clientHeight < NEAR_BOTTOM_PX
}

function scrollToBottom(smooth = false) {
  if (!scrollContainer) return
  scrollContainer.scrollTo({ top: scrollContainer.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

function onContainerScroll() {
  if (!spy.live) return
  const near = isNearBottom()
  stickToBottom = near
  if (near) showFollowButton.value = false
}

function onFollowClick() {
  stickToBottom = true
  showFollowButton.value = false
  scrollToBottom(true)
}

// header sticky "Turno N": misura l'altezza di TimeControls (sticky, sopra
// la timeline) per evitare che i due sticky si sovrappongano, senza dover
// toccare quel componente.
const stickyOffset = ref(44)
let resizeObserver: ResizeObserver | null = null

function measureStickyOffset() {
  const controls = document.querySelector('.time-controls') as HTMLElement | null
  if (controls) stickyOffset.value = controls.getBoundingClientRect().height
}

onMounted(() => {
  if (rootEl.value) scrollContainer = findScrollContainer(rootEl.value)
  scrollContainer?.addEventListener('scroll', onContainerScroll)
  measureStickyOffset()
  resizeObserver = new ResizeObserver(measureStickyOffset)
  const controls = document.querySelector('.time-controls')
  if (controls) resizeObserver.observe(controls)
  void nextTick(() => scrollToBottom())
})

onBeforeUnmount(() => {
  scrollContainer?.removeEventListener('scroll', onContainerScroll)
  resizeObserver?.disconnect()
})

watch(
  () => spy.visibleEvents.length,
  () => {
    if (!spy.live) return
    if (stickToBottom) {
      void nextTick(() => scrollToBottom())
    } else {
      showFollowButton.value = true
    }
  }
)

watch(
  () => spy.live,
  (isLive) => {
    if (isLive) {
      stickToBottom = true
      showFollowButton.value = false
      void nextTick(() => scrollToBottom())
    }
  }
)

watch(
  () => spy.cursor,
  (idx) => {
    if (spy.live) return
    const evt = spy.events[idx]
    if (!evt || !rootEl.value) return
    void nextTick(() => {
      const el = rootEl.value?.querySelector(`[data-event-id="${evt.id}"]`)
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
  }
)

watch(
  () => spy.currentSessionId,
  () => {
    stickToBottom = true
    showFollowButton.value = false
    void nextTick(() => scrollToBottom())
  }
)
</script>

<template>
  <div ref="rootEl" class="timeline-view">
    <p v-if="groups.length === 0" class="empty">Nessun evento in questa sessione (ancora).</p>
    <TransitionGroup v-else name="group" tag="div" class="groups">
      <TurnGroup v-for="g in groups" :key="g.key" :group="g" :sticky-offset="stickyOffset" />
    </TransitionGroup>

    <footer v-if="groups.length" class="legend" aria-label="legenda">
      <span class="item"><span class="swatch" style="background-color: var(--accent)"></span>round trip</span>
      <span class="item"><span class="glyph" style="color: var(--accent-live)">▶</span>prompt utente</span>
      <span class="item"><span class="glyph">🔧</span>tool_use</span>
      <span class="item"><span class="swatch" style="background-color: var(--muted)"></span>hook</span>
      <span class="item"><span class="glyph">🔌</span>mcp</span>
      <span class="item"><span class="glyph">🤖</span>subagente</span>
    </footer>

    <button v-if="showFollowButton" class="follow-btn" @click="onFollowClick">⤓ nuovi eventi</button>
  </div>
</template>

<style scoped>
.timeline-view {
  position: relative;
  flex: 1;
  padding: 0 0 3rem;
  min-height: 100%;
}

.empty {
  padding: 2rem 1.5rem;
  color: var(--muted);
  font-style: italic;
}

.groups {
  display: flex;
  flex-direction: column;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
  padding: 0.6rem 1.5rem 0;
  margin-top: 0.4rem;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 0.72rem;
}

.legend .item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.legend .swatch {
  width: 10px;
  height: 3px;
  border-radius: 2px;
}

.legend .glyph {
  font-size: 0.78rem;
  line-height: 1;
}

.follow-btn {
  position: sticky;
  bottom: 16px;
  left: 100%;
  transform: translateX(-100%);
  width: fit-content;
  background-color: var(--accent);
  color: #06152b;
  border: none;
  border-radius: 999px;
  padding: 0.45rem 1rem;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
  margin-right: 1.25rem;
}

.follow-btn:hover {
  filter: brightness(1.08);
}

.group-enter-active,
.group-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.group-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}

.group-leave-to {
  opacity: 0;
}
</style>
