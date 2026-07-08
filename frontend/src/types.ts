/**
 * Types shared between the store, API client, and components.
 *
 * They mirror the shapes produced by server/agentspy_server/store.py:
 * - Session <- Store.get_sessions()
 * - EventSummary <- Store._event_summary() (used by get_session_events)
 * - EventDetail <- Store.get_event() normalized by the client (see
 *   api/client.ts: the raw DB row is "flat", without nested usage,
 *   duration_s, or snippet; the client rebuilds them for consistency with
 *   EventSummary).
 * - StatsItem <- Store.get_session_stats()
 */

/** Token count for a round trip or session aggregate. */
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
  /** null for top-level sessions (not subagents). */
  parent_session_id: string | null
  /** id of the agent/subagent assigned by the correlator, if present. */
  agent_id: string | null
  started_at: number | null
  /** null while the session is live. */
  ended_at: number | null
  live: boolean
  /** session working directory (from the hooks); used to relativize paths. */
  cwd?: string | null
  /** number of distinct turn_index values seen in the session's events. */
  turns: number
  round_trips: number
  /** max(ts_end) - min(ts_start) across the session's events; null if not computable. */
  duration_s: number | null
  /** tokens for this session alone. */
  usage: Usage
  /** tokens for this session plus all its descendants (subagents). */
  usage_incl_children: Usage
}

export type EventKind = 'round_trip' | 'hook' | 'mcp'

/**
 * Lightweight row for event lists (timeline, context-fill): no full
 * payload, loaded lazily with fetchEventDetail/select().
 */
export interface EventSummary {
  id: number
  kind: EventKind
  /** hook_event_name for kind='hook', "<server>:<method>" for kind='mcp', null for round_trip. */
  subkind: string | null
  session_id: string | null
  turn_index: number | null
  agent_id: string | null
  ts_start: number | null
  /** ts_end - ts_start; null if the event has no ts_end yet (in progress). */
  duration_s: number | null
  /** time-to-first-byte for a streaming round trip; null otherwise. */
  ttfb_s: number | null
  model: string | null
  status: number | null
  stop_reason: string | null
  usage: Usage
  tool_names: string[]
  /** for round trips: tools called in the response, with an argument hint. */
  tool_uses?: { name: string; hint: string }[]
  /** for Pre/PostToolUse hooks: hint of the tool's argument. */
  tool_hint?: string
  /** short text excerpt (first ~160 chars) for the list preview. */
  snippet: string
  /**
   * For round trips: the first *user* message of the request — the delegated
   * task inside a subagent's session, the initial input for service traffic.
   * Empty for other event kinds. Used as the trigger bubble when no
   * UserPromptSubmit hook exists (see TimelineView fallback).
   */
  input_snippet: string
}

/** Full row (GET /api/events/:id): EventSummary + full payload. */
/**
 * Un elemento che compone la richiesta all'LLM (inventario didattico).
 * Nessun contenuto: solo identità + dimensione. Calcolato lato server da
 * context_artifacts.py sul request.body.
 */
export type ArtifactKind = 'system' | 'claude-md' | 'memory' | 'image' | 'at-file' | 'tools'
export interface ContextArtifact {
  kind: ArtifactKind
  label: string
  path?: string | null
  description?: string | null
  chars?: number | null
  count?: number | null
  media_type?: string | null
}

export interface EventDetail extends EventSummary {
  ts_end: number | null
  /**
   * Full round trip payload: payload.request.body has system/tools/messages
   * exactly as sent; payload.response.message is the response reconstructed
   * from SSE streaming. For hook/mcp the shape varies (see ingest.py); treat
   * it as raw data to explore in the UI.
   */
  payload: unknown
  /** Inventario degli elementi del contesto della richiesta. */
  artifacts?: ContextArtifact[]
}

/** Series point for the context-fill panel (one round trip). */
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
  /** char (not token) estimates of the request's system/tools/messages; null if unavailable. */
  system_chars: number | null
  tools_chars: number | null
  messages_chars: number | null
  /** Inventario degli elementi del contesto per questo round trip. */
  artifacts?: ContextArtifact[]
}

export type WsMessage =
  | { type: 'hello'; sessions: Session[] }
  | { type: 'event'; event: EventSummary }
  | { type: 'session'; session: Session }
  | { type: 'session_removed'; id: string }
