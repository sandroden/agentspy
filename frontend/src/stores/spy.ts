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
import type { EventDetail, EventSummary, Session, StatsItem, WsMessage } from '../types'

export interface SessionNode extends Session {
  children: SessionNode[]
}

export const useSpyStore = defineStore('spy', () => {
  // -- state ------------------------------------------------------------
  const sessions = ref<Record<string, Session>>({})
  const currentSessionId = ref<string | null>(null)
  /** eventi della sessione aperta, ordinati per ts_start crescente. */
  const events = ref<EventSummary[]>([])
  const stats = ref<StatsItem[]>([])
  /** cache stats per sessione, usata dalla dashboard (indipendente da `stats`). */
  const statsBySession = ref<Record<string, StatsItem[]>>({})
  const live = ref(true)
  /** indice (in `events`) dell'ultimo evento visibile. */
  const cursor = ref(-1)
  const selectedEventId = ref<number | null>(null)
  const detailCache = ref<Record<number, EventDetail>>({})
  const detailLoading = ref(false)
  const wsConnected = ref(false)
  /** contatore eventi non visti per sessione (per il badge in sidebar); azzerato aprendo la sessione. */
  const unseenCounts = ref<Record<string, number>>({})

  let streamHandle: StreamHandle | null = null

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

  // -- helpers --------------------------------------------------------------
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

  async function openSession(id: string) {
    currentSessionId.value = id
    unseenCounts.value = { ...unseenCounts.value, [id]: 0 }
    const [evts, st] = await Promise.all([fetchSessionEvents(id), fetchSessionStats(id)])
    events.value = evts
    stats.value = st
    cursor.value = events.value.length - 1
    live.value = true
  }

  function onWsMessage(msg: WsMessage) {
    if (msg.type === 'hello') {
      replaceSessions(msg.sessions)
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
    if (detailCache.value[eventId]) return
    detailLoading.value = true
    try {
      const detail = await fetchEventDetail(eventId)
      detailCache.value = { ...detailCache.value, [eventId]: detail }
    } finally {
      detailLoading.value = false
    }
  }

  function clearSelection() {
    selectedEventId.value = null
  }

  /**
   * Rimuove localmente una sessione dallo stato (usata sia dall'azione di
   * eliminazione sia dal messaggio WS session_removed). Se è quella aperta,
   * azzera la selezione e gli eventi correnti: la view farà l'eventuale
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
  }

  /**
   * Elimina le sessioni indicate via API (cascata sui figli lato server) e
   * aggiorna lo stato locale senza dipendere dal WS, che potrebbe non essere
   * connesso. Ritorna gli id effettivamente rimossi (inclusi i discendenti).
   */
  async function deleteSessions(ids: string[]): Promise<string[]> {
    const deleted = await apiDeleteSessions(ids)
    // rimuovi sia gli id richiesti sia i discendenti riportati dal server.
    for (const id of new Set([...ids, ...deleted])) removeSessionLocal(id)
    return deleted
  }

  /**
   * Carica (con cache) le stats di una sessione per la dashboard, senza
   * toccare `stats`/`currentSessionId` usati da SessionView. `force` rilegge
   * ignorando la cache (utile per sessioni live che accumulano round trip).
   */
  async function loadStatsFor(id: string, force = false): Promise<StatsItem[]> {
    if (!force && statsBySession.value[id]) return statsBySession.value[id]
    const st = await fetchSessionStats(id)
    statsBySession.value = { ...statsBySession.value, [id]: st }
    return st
  }

  return {
    // state
    sessions,
    currentSessionId,
    events,
    stats,
    statsBySession,
    live,
    cursor,
    selectedEventId,
    detailCache,
    detailLoading,
    wsConnected,
    unseenCounts,
    // getters
    sessionTree,
    currentSession,
    visibleEvents,
    selectedDetail,
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
  }
})
