import type { EventDetail, EventSummary, Session, StatsItem, Usage, WsMessage } from '../types'

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} su ${url}`)
  }
  return (await response.json()) as T
}

type NullableUsage = {
  [K in keyof Usage]?: Usage[K] | null
}

function normalizeUsage(u: NullableUsage | null | undefined): Usage {
  return {
    input_tokens: u?.input_tokens ?? 0,
    output_tokens: u?.output_tokens ?? 0,
    cache_read_tokens: u?.cache_read_tokens ?? 0,
    cache_write_tokens: u?.cache_write_tokens ?? 0,
  }
}

export async function fetchSessions(): Promise<Session[]> {
  return getJson<Session[]>('/api/sessions')
}

export async function fetchSessionEvents(id: string): Promise<EventSummary[]> {
  const rows = await getJson<EventSummary[]>(`/api/sessions/${id}/events`)
  // le colonne token possono essere NULL in DB per eventi hook/mcp: normalizza
  // a 0 perché il resto della UI tratta Usage come sempre numerico.
  return rows.map((r) => ({ ...r, usage: normalizeUsage(r.usage) }))
}

export async function fetchSessionStats(id: string): Promise<StatsItem[]> {
  return getJson<StatsItem[]>(`/api/sessions/${id}/stats`)
}

/**
 * Forma grezza restituita da GET /api/events/:id (Store.get_event): è la riga
 * DB "piatta", con i token come colonne separate (non un oggetto usage), senza
 * duration_s e senza snippet precalcolato. fetchEventDetail la normalizza
 * nella forma EventDetail = EventSummary & {ts_end, payload} per uniformità
 * con fetchSessionEvents.
 */
interface RawEventRow {
  id: number
  session_id: string | null
  kind: EventSummary['kind']
  subkind: string | null
  turn_index: number | null
  agent_id: string | null
  ts_start: number | null
  ts_end: number | null
  ttfb_s: number | null
  model: string | null
  status: number | null
  stop_reason: string | null
  input_tokens: number | null
  output_tokens: number | null
  cache_read_tokens: number | null
  cache_write_tokens: number | null
  tool_names: string[] | null
  payload: unknown
}

/** Ricalca Store._snippet_from_payload lato client, perché get_event non la include. */
function extractSnippet(kind: string, subkind: string | null, payload: unknown): string {
  if (!payload || typeof payload !== 'object') return ''
  const p = payload as Record<string, any>
  try {
    if (kind === 'round_trip') {
      const message = p.response?.message ?? {}
      for (const block of message.content ?? []) {
        if (block?.type === 'text' && block.text) return String(block.text).slice(0, 160)
        if (block?.type === 'tool_use') return `tool_use: ${block.name}`
      }
      const messages = p.request?.body?.messages ?? []
      if (messages.length) {
        const content = messages[messages.length - 1]?.content
        if (typeof content === 'string') return content.slice(0, 160)
      }
      return ''
    }
    if (kind === 'hook' || kind === 'mcp') return subkind ?? ''
  } catch {
    return ''
  }
  return ''
}

export async function fetchEventDetail(id: number): Promise<EventDetail> {
  const raw = await getJson<RawEventRow>(`/api/events/${id}`)
  const duration_s =
    raw.ts_end != null && raw.ts_start != null ? raw.ts_end - raw.ts_start : null
  return {
    id: raw.id,
    kind: raw.kind,
    subkind: raw.subkind,
    session_id: raw.session_id,
    turn_index: raw.turn_index,
    agent_id: raw.agent_id,
    ts_start: raw.ts_start,
    ts_end: raw.ts_end,
    duration_s,
    ttfb_s: raw.ttfb_s,
    model: raw.model,
    status: raw.status,
    stop_reason: raw.stop_reason,
    usage: normalizeUsage(raw),
    tool_names: raw.tool_names ?? [],
    snippet: extractSnippet(raw.kind, raw.subkind, raw.payload),
    payload: raw.payload,
  }
}

export interface StreamHandle {
  close(): void
}

/**
 * Apre il WebSocket /ws con riconnessione automatica (backoff 1s→10s max).
 * Alla riconnessione il server rimanda un 'hello' con l'elenco sessioni
 * completo: onMessage lo riceve come un messaggio normale, nessuna gestione
 * speciale richiesta lato chiamante.
 *
 * onStatusChange (opzionale) segnala connesso/disconnesso, utile per
 * l'indicatore WS in UI.
 */
export function openStream(
  onMessage: (message: WsMessage) => void,
  onStatusChange?: (connected: boolean) => void
): StreamHandle {
  let ws: WebSocket | null = null
  let closedByUser = false
  let reconnectDelay = 1000
  const maxDelay = 10000
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleReconnect() {
    if (reconnectTimer != null) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, reconnectDelay)
    reconnectDelay = Math.min(reconnectDelay * 2, maxDelay)
  }

  function connect() {
    const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
    ws = new WebSocket(url)
    ws.addEventListener('open', () => {
      reconnectDelay = 1000
      onStatusChange?.(true)
    })
    ws.addEventListener('message', (ev) => {
      try {
        onMessage(JSON.parse(ev.data) as WsMessage)
      } catch (err) {
        console.error('openStream: messaggio WS non valido', err)
      }
    })
    ws.addEventListener('close', () => {
      onStatusChange?.(false)
      if (!closedByUser) scheduleReconnect()
    })
    ws.addEventListener('error', () => {
      ws?.close()
    })
  }

  connect()

  return {
    close() {
      closedByUser = true
      if (reconnectTimer != null) clearTimeout(reconnectTimer)
      ws?.close()
    },
  }
}
