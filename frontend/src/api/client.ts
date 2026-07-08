import type { ContextArtifact, EventDetail, EventSummary, Session, StatsItem, Usage, WsMessage } from '../types'

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} for ${url}`)
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
  // token columns can be NULL in the DB for hook/mcp events: normalize to 0
  // because the rest of the UI treats Usage as always numeric.
  return rows.map((r) => ({ ...r, usage: normalizeUsage(r.usage) }))
}

export async function fetchSessionStats(id: string): Promise<StatsItem[]> {
  return getJson<StatsItem[]>(`/api/sessions/${id}/stats`)
}

/**
 * Deletes the given sessions (with their descendants, cascading server-side).
 * Returns the full list of ids actually removed.
 */
export async function deleteSessions(ids: string[]): Promise<string[]> {
  const response = await fetch('/api/sessions/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} for /api/sessions/delete`)
  }
  const body = (await response.json()) as { deleted: string[] }
  return body.deleted ?? []
}

/**
 * Raw shape returned by GET /api/events/:id (Store.get_event): it's the
 * "flat" DB row, with tokens as separate columns (not a usage object),
 * without duration_s and without a precomputed snippet. fetchEventDetail
 * normalizes it into the EventDetail = EventSummary & {ts_end, payload}
 * shape for consistency with fetchSessionEvents.
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
  artifacts?: ContextArtifact[]
}

/** Mirrors Store._snippet_from_payload client-side, since get_event doesn't include it. */
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

/** Mirrors Store._command_snippet: a clean "/name args" for an expanded
 *  slash-command / skill, instead of the wrapper XML + injected SKILL.md. */
function commandSnippet(text: string): string | null {
  if (!text.includes('<command-name>')) return null
  const name = text.match(/<command-name>\s*([\s\S]*?)\s*<\/command-name>/)?.[1]?.trim()
  if (!name) return null
  const args = text.match(/<command-args>\s*([\s\S]*?)\s*<\/command-args>/)?.[1]?.trim() ?? ''
  return `${name} ${args}`.trim().slice(0, 160)
}

/** Mirrors Store._input_snippet_from_payload client-side (first user message of
 *  the request, skipping <system-reminder> blocks — the delegated task). */
function extractInputSnippet(kind: string, payload: unknown): string {
  if (!payload || typeof payload !== 'object' || kind !== 'round_trip') return ''
  const p = payload as Record<string, any>
  try {
    for (const message of p.request?.body?.messages ?? []) {
      if (message?.role !== 'user') continue
      const content = message.content
      if (typeof content === 'string') return content.trim().slice(0, 160)
      if (Array.isArray(content)) {
        for (const block of content) {
          if (block?.type !== 'text') continue
          const text = String(block.text ?? '').trim()
          if (!text || text.startsWith('<system-reminder>')) continue
          return commandSnippet(text) ?? text.slice(0, 160)
        }
      }
      return ''
    }
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
    input_snippet: extractInputSnippet(raw.kind, raw.payload),
    payload: raw.payload,
    artifacts: raw.artifacts ?? [],
  }
}

export interface StreamHandle {
  close(): void
}

/**
 * Opens the /ws WebSocket with automatic reconnection (backoff 1s→10s max).
 * On reconnection the server resends a 'hello' with the full session list:
 * onMessage receives it as a normal message, no special handling required
 * on the caller's side.
 *
 * onStatusChange (optional) signals connected/disconnected, useful for the
 * WS indicator in the UI.
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
        console.error('openStream: invalid WS message', err)
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
