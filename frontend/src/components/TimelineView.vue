<script setup lang="ts">
// Vertical timeline (time top-to-bottom), grouped by turn_index and rendered
// as a Trigger | Claude (LLM) | Tools swimlane. Reads ONLY spy.visibleEvents
// (already filtered by live/pause/cursor) + spy.sessions (to find child
// sub-agents) and spy.detailCache (best-effort, to enrich the turn header
// with the real prompt once it has been loaded by a previous click).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useSpyStore } from '../stores/spy'
import type { EventSummary, Session } from '../types'
import Glossary from './timeline/Glossary.vue'
import SessionSummaryBar from './timeline/SessionSummaryBar.vue'
import TurnGroup from './timeline/TurnGroup.vue'

// Dismissing the glossary tips reveals the session usage summary in its
// place instead (see SessionSummaryBar.vue); persisted like before.
const GLOSSARY_KEY = 'agentspy.showGlossary'
const showGlossary = ref(localStorage.getItem(GLOSSARY_KEY) !== '0')
watch(showGlossary, (v) => localStorage.setItem(GLOSSARY_KEY, v ? '1' : '0'))

export interface SubagentRowData {
  agentId: string
  childId: string | null
  ts: number
  label: string
}

export type TimelineRow =
  | { rowKind: 'event'; event: EventSummary }
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
 * Groups spy.visibleEvents by turn in a single O(n) pass, avoiding repeated
 * work in the template. Sub-agents are detected two ways (see
 * PLAN.md/correlate.py): (a) an event in the current session already carries
 * an `agent_id` (hook schema not yet empirically verified for SubagentStart
 * on the parent side); (b) a child session exists (parent_session_id ===
 * current session) whose agent_id never shows up in any event — in that case
 * a time-based marker is inserted from its `started_at`. Either way, only a
 * pointer block is shown, never the child's own events.
 */
const groups = computed<TimelineGroup[]>(() => {
  // note: PostToolUse events are already filtered at the source (stores/spy.ts)
  const evts = spy.visibleEvents
  const parentId = spy.currentSessionId
  // agent_id of the OPEN session (if it is itself a sub-agent): an event
  // reporting it is just the echo of its own correlation state (e.g.
  // SubagentStart/Stop within the child session itself), not a grandchild.
  const ownAgentId = spy.currentSession?.agent_id ?? null
  const children: Session[] = parentId
    ? Object.values(spy.sessions).filter((s) => s.parent_session_id === parentId && s.agent_id)
    : []
  const claimedAgentIds = new Set(
    evts
      .filter((e): e is EventSummary & { agent_id: string } => !!e.agent_id && e.agent_id !== ownAgentId)
      .map((e) => e.agent_id)
  )
  // while paused (or with the cursor rewound) `evts` only covers time up to
  // the cursor: a child born after that instant must not show up yet, or the
  // timeline would "get ahead" of the cursor.
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
  // ts_start of every anchor per group, for the turn header's time/duration —
  // tracked independently of `rows` since hook anchors (e.g. UserPromptSubmit,
  // which usually opens the turn) no longer become visible rows.
  const tsByKey = new Map<string, number[]>()
  function noteTs(key: string, ts: number) {
    const arr = tsByKey.get(key)
    if (arr) arr.push(ts)
    else tsByKey.set(key, [ts])
  }

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

    noteTs(group.key, anchor.ts)

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
        // extends the already-open sub-agent block: no new row
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
    lastEndTs = rowEnd
    // Hook events (PreToolUse, UserPromptSubmit, ...) don't get their own
    // swimlane row: the tool call is already shown via the round trip's own
    // tool_uses, and having hooks "as such" appear in the timeline would
    // teach a Claude Code implementation detail nobody asked to learn. They
    // still contribute data (turn grouping above, prompt snippet below).
    if (e.kind === 'round_trip') {
      group.rows.push({ rowKind: 'event', event: e })
      group.roundTrips++
      group.outputTokens += e.usage.output_tokens
    } else if (e.kind === 'mcp') {
      group.rows.push({ rowKind: 'event', event: e })
    }
    if (e.kind === 'hook' && e.subkind === 'UserPromptSubmit' && !group.promptSnippet && e.snippet) {
      // e.snippet already carries the real prompt text for this hook (see
      // store.py:_snippet_from_payload) — no need to wait for a click to
      // populate spy.detailCache, which never happens since UserPromptSubmit
      // hooks don't render their own row (see comment above).
      group.promptSnippet = e.snippet
    }
  }

  for (const key of order) {
    const g = byKey.get(key) as TimelineGroup
    if (!g.promptSnippet) {
      // No UserPromptSubmit hook fired for this turn — happens inside a
      // subagent's session (trigger = the delegated task) and for service
      // traffic. Use the round trip's *input* (first user message), not its
      // snippet, which is the response ("tool_use: Bash").
      const firstRoundTrip = g.rows.find(
        (r): r is TimelineRow & { rowKind: 'event' } => r.rowKind === 'event' && r.event.kind === 'round_trip'
      )
      if (firstRoundTrip) g.promptSnippet = firstRoundTrip.event.input_snippet
    }
    const timestamps = tsByKey.get(key) ?? []
    if (timestamps.length) {
      g.startTs = Math.min(...timestamps)
      g.durationS = Math.max(...timestamps) - g.startTs
    }
  }

  // A turn made only of hook events (typically the startup traffic before
  // the first prompt) now has zero visible rows — or only a 'gap' separator,
  // which isn't real content either. Skip it rather than showing an empty
  // header + lanehead with nothing meaningful under it.
  return order
    .map((k) => byKey.get(k) as TimelineGroup)
    .filter((g) => g.rows.some((r) => r.rowKind !== 'gap'))
})

// -- "follow" scroll -----------------------------------------------------
const rootEl = ref<HTMLElement | null>(null)
const showFollowButton = ref(false)
let scrollContainer: HTMLElement | null = null
let stickToBottom = true
const NEAR_BOTTOM_PX = 150

function findScrollContainer(el: HTMLElement | null): HTMLElement {
  // Based purely on style (not on scrollHeight > clientHeight): at
  // onMounted the real content hasn't arrived yet (async fetch), so
  // `.center` might not "overflow" yet despite being the real scroll
  // container — checking overflow-y is stable regardless of content already
  // loaded.
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

// sticky "Turn N" header: measures TimeControls' height (sticky, above the
// timeline) to keep the two sticky elements from overlapping, without having
// to touch that component.
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
    <template v-if="groups.length">
      <Glossary v-if="showGlossary" v-model="showGlossary" />
      <SessionSummaryBar v-else @show-tips="showGlossary = true" />
    </template>
    <p v-if="groups.length === 0" class="empty">No events in this session (yet).</p>
    <TransitionGroup v-else name="group" tag="div" class="groups">
      <TurnGroup v-for="g in groups" :key="g.key" :group="g" :sticky-offset="stickyOffset" />
    </TransitionGroup>

    <button v-if="showFollowButton" class="follow-btn" @click="onFollowClick">⤓ new events</button>
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
