/**
 * Tipi condivisi fra store, client API e componenti.
 *
 * Rispecchiano le forme prodotte da server/agentspy_server/store.py:
 * - Session <- Store.get_sessions()
 * - EventSummary <- Store._event_summary() (usata da get_session_events)
 * - EventDetail <- Store.get_event() normalizzato dal client (vedi
 *   api/client.ts: la riga grezza del DB è "piatta", senza usage annidato,
 *   duration_s o snippet; il client li ricostruisce per uniformità con
 *   EventSummary).
 * - StatsItem <- Store.get_session_stats()
 */

/** Conteggio token di un round trip o aggregato di sessione. */
export interface Usage {
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
}

export interface Session {
  id: string
  tag: string | null
  title: string | null
  model: string | null
  /** null per le sessioni top-level (non subagenti). */
  parent_session_id: string | null
  /** id dell'agente/subagente assegnato dal correlatore, se presente. */
  agent_id: string | null
  started_at: number | null
  /** null finché la sessione è live. */
  ended_at: number | null
  live: boolean
  /** working directory della sessione (dagli hook); usata per relativizzare i path. */
  cwd?: string | null
  /** numero di turn_index distinti visti negli eventi della sessione. */
  turns: number
  round_trips: number
  /** max(ts_end) - min(ts_start) fra gli eventi della sessione; null se non calcolabile. */
  duration_s: number | null
  /** token della sola sessione. */
  usage: Usage
  /** token della sessione + di tutti i suoi discendenti (subagenti). */
  usage_incl_children: Usage
}

export type EventKind = 'round_trip' | 'hook' | 'mcp'

/**
 * Riga leggera per le liste evento (timeline, context-fill): niente
 * payload completo, caricato lazy con fetchEventDetail/select().
 */
export interface EventSummary {
  id: number
  kind: EventKind
  /** hook_event_name per kind='hook', "<server>:<metodo>" per kind='mcp', null per round_trip. */
  subkind: string | null
  session_id: string | null
  turn_index: number | null
  agent_id: string | null
  ts_start: number | null
  /** ts_end - ts_start; null se l'evento non ha ancora un ts_end (in corso). */
  duration_s: number | null
  /** time-to-first-byte per round trip in streaming; null altrimenti. */
  ttfb_s: number | null
  model: string | null
  status: number | null
  stop_reason: string | null
  usage: Usage
  tool_names: string[]
  /** per i round trip: tool chiamati nella risposta, con un indizio dell'argomento. */
  tool_uses?: { name: string; hint: string }[]
  /** per gli hook Pre/PostToolUse: indizio dell'argomento del tool. */
  tool_hint?: string
  /** breve estratto testuale (primi ~160 char) per l'anteprima in lista. */
  snippet: string
}

/** Riga completa (GET /api/events/:id): EventSummary + payload integrale. */
export interface EventDetail extends EventSummary {
  ts_end: number | null
  /**
   * Payload completo del round trip: payload.request.body ha
   * system/tools/messages così come inviati; payload.response.message è la
   * risposta ricostruita dallo streaming SSE. Per hook/mcp la forma varia
   * (vedi ingest.py); trattare come dato grezzo da esplorare in UI.
   */
  payload: unknown
}

/** Punto della serie per il pannello di riempimento contesto (un round trip). */
export interface StatsItem {
  event_id: number
  turn_index: number | null
  ts_start: number | null
  ttfb_s: number | null
  duration_s: number | null
  model: string | null
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  /** stime char (non token) di system/tools/messages della richiesta; null se non disponibili. */
  system_chars: number | null
  tools_chars: number | null
  messages_chars: number | null
}

export type WsMessage =
  | { type: 'hello'; sessions: Session[] }
  | { type: 'event'; event: EventSummary }
  | { type: 'session'; session: Session }
  | { type: 'session_removed'; id: string }
