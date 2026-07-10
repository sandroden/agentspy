import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteSessions as apiDeleteSessions,
  fetchEventDetail,
  fetchSessionEvents,
  fetchSessionStats,
  fetchSessions,
  openStream,
  type StreamHandle,
} from '../api/client'
import type { ContextArtifact, EventDetail, EventSummary, Session, StatsItem, WsMessage } from '../types'

/** Chiave d'identità di un artefatto per il calcolo "prima comparsa". */
function artifactKey(a: ContextArtifact): string {
  return `${a.kind}|${a.path ?? a.label}`
}

export interface SessionNode extends Session {
  children: SessionNode[]
}

export const useSpyStore = defineStore('spy', () => {
  // -- state ------------------------------------------------------------
  const sessions = ref<Record<string, Session>>({})
  const currentSessionId = ref<string | null>(null)
  /** "featured" session in the dashboard; kept in the store so the sidebar
   * can set it without changing route when already on the dashboard. */
  const featuredSessionId = ref<string | null>(null)
  /** events of the open session, sorted by ascending ts_start. */
  const events = ref<EventSummary[]>([])
  const stats = ref<StatsItem[]>([])
  /** per-session stats cache, used by the dashboard (independent of `stats`). */
  const statsBySession = ref<Record<string, StatsItem[]>>({})
  const live = ref(true)
  /** index (in `events`) of the last visible event. */
  const cursor = ref(-1)
  const selectedEventId = ref<number | null>(null)
  const detailCache = ref<Record<number, EventDetail>>({})
  const detailLoading = ref(false)
  /** true when the last fetchEventDetail for the selected event failed (lets the
   * UI show a retry affordance instead of a permanent spinner). */
  const detailError = ref(false)
  const wsConnected = ref(false)
  /** unseen event counter per session (for the sidebar badge); reset when opening the session. */
  const unseenCounts = ref<Record<string, number>>({})
  /** modale "cosa si porta dietro il contesto": aperta al click su una chip. */
  const contextInventoryOpen = ref(false)

  let streamHandle: StreamHandle | null = null
  /** request token for openSession: guards against out-of-order fetch results
   * when the user switches session quickly (click A → B before A resolves). */
  let openSeq = 0
  /** whether the first WS 'hello' has been seen: the initial hello is redundant
   * with the route's own openSession, only reconnection hellos need a reload. */
  let helloSeen = false

  // -- getters ------------------------------------------------------------
  const sessionTree = computed<SessionNode[]>(() => {
    const byParent = new Map<string | null, Session[]>()
    for (const s of Object.values(sessions.value)) {
      const key = s.parent_session_id
      const bucket = byParent.get(key)
      if (bucket) bucket.push(s)
      else byParent.set(key, [s])
    }
    const sortDesc = (a: Session, b: Session) => (b.started_at ?? 0) - (a.started_at ?? 0)
    const build = (parentId: string | null): SessionNode[] =>
      (byParent.get(parentId) ?? [])
        .slice()
        .sort(sortDesc)
        .map((s) => ({ ...s, children: build(s.id) }))
    return build(null)
  })

  const currentSession = computed<Session | null>(() =>
    currentSessionId.value ? (sessions.value[currentSessionId.value] ?? null) : null
  )

  const visibleEvents = computed<EventSummary[]>(() =>
    live.value ? events.value : events.value.slice(0, cursor.value + 1)
  )

  const selectedDetail = computed<EventDetail | null>(() =>
    selectedEventId.value != null ? (detailCache.value[selectedEventId.value] ?? null) : null
  )

  /**
   * Per ogni round trip, gli elementi del contesto visti per la PRIMA volta in
   * quel round trip (la "canzone del mercato" resa inline): al primo RT compare
   * la base del contesto, ai successivi solo le aggiunte. Mappa event_id →
   * artefatti nuovi, calcolata scorrendo `stats` in ordine cronologico.
   */
  const newArtifactsByEvent = computed<Record<number, ContextArtifact[]>>(() => {
    const seen = new Set<string>()
    const out: Record<number, ContextArtifact[]> = {}
    for (const s of stats.value) {
      const fresh: ContextArtifact[] = []
      for (const a of s.artifacts ?? []) {
        const key = artifactKey(a)
        if (seen.has(key)) continue
        seen.add(key)
        fresh.push(a)
      }
      if (fresh.length) out[s.event_id] = fresh
    }
    return out
  })

  /** Inventario cumulativo dell'intera sessione, in ordine di prima comparsa. */
  const cumulativeArtifacts = computed<ContextArtifact[]>(() => {
    const seen = new Set<string>()
    const out: ContextArtifact[] = []
    for (const s of stats.value) {
      for (const a of s.artifacts ?? []) {
        const key = artifactKey(a)
        if (seen.has(key)) continue
        seen.add(key)
        out.push(a)
      }
    }
    return out
  })

  // -- helpers --------------------------------------------------------------
  /**
   * Pre/PostToolUse hook events never enter `events` at all: didactically the
   * tool call is ONE thing, already rendered via the round trip's own
   * tool_uses; the hooks are a detail of Claude Code's mechanism and, if
   * included, would produce "empty" player steps (cursor landing on events
   * the timeline doesn't show, with no visible change on screen).
   */
  function isTimelineEvent(e: EventSummary): boolean {
    return !(e.kind === 'hook' && (e.subkind === 'PostToolUse' || e.subkind === 'PreToolUse'))
  }

  function replaceSessions(list: Session[]) {
    const map: Record<string, Session> = {}
    for (const s of list) map[s.id] = s
    sessions.value = map
  }

  function insertEventSorted(evt: EventSummary) {
    const idx = events.value.findIndex((e) => (e.ts_start ?? 0) > (evt.ts_start ?? 0))
    if (idx === -1) events.value.push(evt)
    else events.value.splice(idx, 0, evt)
  }

  // -- actions ------------------------------------------------------------
  async function init() {
    replaceSessions(await fetchSessions())
    streamHandle?.close()
    streamHandle = openStream(onWsMessage, (connected) => {
      wsConnected.value = connected
    })
  }

  /**
   * Opens (or reloads) a session and loads its events/stats.
   *
   * `preservePlayback` (used by the reconnection reload) keeps the current
   * live/cursor state instead of jumping to the live edge: a background reload
   * while the user is paused on a round trip must not strip them off it.
   */
  async function openSession(id: string, preservePlayback = false) {
    const seq = ++openSeq
    const switching = currentSessionId.value !== id
    // Remember the round trip the user is paused on, to restore it after reload.
    const anchorId = preservePlayback ? (events.value[cursor.value]?.id ?? null) : null
    currentSessionId.value = id
    unseenCounts.value = { ...unseenCounts.value, [id]: 0 }
    // Switching session clears immediately: a WS 'event' arriving during the
    // await lands (via onWsMessage → insertEventSorted, since currentSessionId
    // is already `id`) in a fresh array, not the previous session's list. On a
    // same-session reload we keep the current list and merge into it below.
    if (switching) {
      events.value = []
      stats.value = []
    }
    const [evts, st] = await Promise.all([fetchSessionEvents(id), fetchSessionStats(id)])
    // A newer openSession superseded this one (fast A→B switch): drop the result.
    if (seq !== openSeq) return
    const timeline = evts.filter(isTimelineEvent)
    // Merge the fetched snapshot with what's already in events.value (WS events
    // that arrived during the await, plus — on a same-session reload — the prior
    // list); dedup by id, since the same round trip can appear in both the
    // snapshot and the stream and insertEventSorted doesn't deduplicate.
    const existing = events.value
    if (existing.length) {
      const byId = new Map<number, EventSummary>()
      for (const e of timeline) byId.set(e.id, e)
      for (const e of existing) byId.set(e.id, e)
      events.value = [...byId.values()].sort((a, b) => (a.ts_start ?? 0) - (b.ts_start ?? 0))
    } else {
      events.value = timeline
    }
    stats.value = st
    if (preservePlayback && !live.value) {
      // Restore the cursor to the same round trip (indices are stable when the
      // gap only appended, but re-find by id to be safe).
      const idx = anchorId != null ? events.value.findIndex((e) => e.id === anchorId) : -1
      cursor.value = idx >= 0 ? idx : Math.min(cursor.value, Math.max(events.value.length - 1, 0))
    } else {
      cursor.value = events.value.length - 1
      live.value = true
    }
  }

  function onWsMessage(msg: WsMessage) {
    if (msg.type === 'hello') {
      replaceSessions(msg.sessions)
      // On a RECONNECTION hello (not the first), reload the open session's
      // events: the round trips from the disconnect window are otherwise lost
      // from the timeline forever (only the sidebar badge would update).
      // preservePlayback keeps a paused user on their round trip.
      if (helloSeen && currentSessionId.value) {
        void openSession(currentSessionId.value, true)
      }
      helloSeen = true
      return
    }
    if (msg.type === 'session') {
      sessions.value = { ...sessions.value, [msg.session.id]: msg.session }
      return
    }
    if (msg.type === 'session_removed') {
      const next = { ...sessions.value }
      delete next[msg.id]
      sessions.value = next
      const nextUnseen = { ...unseenCounts.value }
      delete nextUnseen[msg.id]
      unseenCounts.value = nextUnseen
      if (currentSessionId.value === msg.id) {
        void fetchSessions().then((list) => {
          replaceSessions(list)
          if (sessions.value[msg.id]) {
            void openSession(msg.id)
          } else {
            currentSessionId.value = null
            events.value = []
            stats.value = []
          }
        })
      }
      return
    }
    if (msg.type === 'event') {
      const evt = msg.event
      if (!isTimelineEvent(evt)) return
      if (evt.session_id === currentSessionId.value) {
        insertEventSorted(evt)
        if (live.value) cursor.value = events.value.length - 1
      } else if (evt.session_id) {
        unseenCounts.value = {
          ...unseenCounts.value,
          [evt.session_id]: (unseenCounts.value[evt.session_id] ?? 0) + 1,
        }
      }
    }
  }

  function pause() {
    live.value = false
  }

  function goLive() {
    cursor.value = events.value.length - 1
    live.value = true
  }

  function setCursor(i: number) {
    const maxIndex = Math.max(events.value.length - 1, 0)
    const clamped = Math.max(0, Math.min(i, maxIndex))
    cursor.value = clamped
    if (clamped < maxIndex) live.value = false
  }

  function step(delta: number) {
    setCursor(cursor.value + delta)
  }

  async function select(eventId: number) {
    selectedEventId.value = eventId
    detailError.value = false
    if (detailCache.value[eventId]) return
    detailLoading.value = true
    try {
      const detail = await fetchEventDetail(eventId)
      if (selectedEventId.value !== eventId) return // selection moved on
      detailCache.value = { ...detailCache.value, [eventId]: detail }
    } catch {
      if (selectedEventId.value === eventId) detailError.value = true
    } finally {
      if (selectedEventId.value === eventId) detailLoading.value = false
    }
  }

  function clearSelection() {
    selectedEventId.value = null
    detailError.value = false
  }

  /**
   * Removes a session locally from state (used both by the delete action and
   * by the WS session_removed message). If it's the currently open one,
   * resets the selection and current events: the view will handle any
   * redirect.
   */
  function removeSessionLocal(id: string) {
    if (sessions.value[id]) {
      const next = { ...sessions.value }
      delete next[id]
      sessions.value = next
    }
    if (unseenCounts.value[id] != null) {
      const nextUnseen = { ...unseenCounts.value }
      delete nextUnseen[id]
      unseenCounts.value = nextUnseen
    }
    if (currentSessionId.value === id) {
      currentSessionId.value = null
      events.value = []
      stats.value = []
    }
    if (featuredSessionId.value === id) featuredSessionId.value = null
  }

  /**
   * Deletes the given sessions via API (cascading to children server-side)
   * and updates local state without depending on the WS, which might not be
   * connected. Returns the ids actually removed (including descendants).
   */
  async function deleteSessions(ids: string[]): Promise<string[]> {
    const deleted = await apiDeleteSessions(ids)
    // remove both the requested ids and the descendants reported by the server.
    for (const id of new Set([...ids, ...deleted])) removeSessionLocal(id)
    return deleted
  }

  /**
   * Loads (with caching) a session's stats for the dashboard, without
   * touching `stats`/`currentSessionId` used by SessionView. `force` reloads
   * bypassing the cache (useful for live sessions that accumulate round trips).
   */
  async function loadStatsFor(id: string, force = false): Promise<StatsItem[]> {
    if (!force && statsBySession.value[id]) return statsBySession.value[id]
    const st = await fetchSessionStats(id)
    statsBySession.value = { ...statsBySession.value, [id]: st }
    return st
  }

  function openContextInventory() {
    contextInventoryOpen.value = true
  }
  function closeContextInventory() {
    contextInventoryOpen.value = false
  }

  return {
    // state
    sessions,
    currentSessionId,
    featuredSessionId,
    events,
    stats,
    statsBySession,
    live,
    cursor,
    selectedEventId,
    detailCache,
    detailLoading,
    detailError,
    wsConnected,
    unseenCounts,
    contextInventoryOpen,
    // getters
    sessionTree,
    currentSession,
    visibleEvents,
    selectedDetail,
    newArtifactsByEvent,
    cumulativeArtifacts,
    // actions
    init,
    openSession,
    onWsMessage,
    pause,
    goLive,
    setCursor,
    step,
    select,
    clearSelection,
    deleteSessions,
    loadStatsFor,
    openContextInventory,
    closeContextInventory,
  }
})
