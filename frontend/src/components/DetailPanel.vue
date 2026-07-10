<script setup lang="ts">
// Detail panel (L4): shows the full payload of the selected event
// (spy.selectedDetail, lazy-fetch handled by the store) in horizontal tabs.
// For round_trip: Summary | Request | Response | Delta | JSON. For hook/mcp:
// Summary | (Call, mcp only) | JSON.
import { computed, provide, ref, watch, watchEffect } from 'vue'
import { useSpyStore } from '../stores/spy'
import { fetchEventDetail } from '../api/client'
import type { EventDetail, EventSummary } from '../types'
import { formatDuration, formatTime, formatTokens } from '../utils/format'
import Collapsible from './detail/Collapsible.vue'
import ContentBlock from './detail/ContentBlock.vue'
import JsonTree from './detail/JsonTree.vue'
import MessageBlock from './detail/MessageBlock.vue'
import { compactViewKey, cwdKey } from './detail/detailKeys'

// -- compact system-reminder view ------------------------------------------
// Collapses <system-reminder> sections inside text blocks (see
// SystemReminderText.vue). Persisted in localStorage and provided to descendants.
const COMPACT_KEY = 'agentspy.compactView'
const compactView = ref(localStorage.getItem(COMPACT_KEY) === '1')
provide(compactViewKey, compactView)
watch(compactView, (v) => localStorage.setItem(COMPACT_KEY, v ? '1' : '0'))

type AnyRecord = Record<string, any>
type TabId = 'summary' | 'request' | 'response' | 'delta' | 'call' | 'json'

const spy = useSpyStore()

const detail = computed<EventDetail | null>(() => spy.selectedDetail)

// session cwd of the selected event, made available to descendants
// (JsonTree, ContentBlock, MessageBlock, SystemReminderText) to relativize
// file paths shown in the payload.
const cwd = computed<string | null | undefined>(() =>
  detail.value?.session_id ? spy.sessions[detail.value.session_id]?.cwd : null
)
provide(cwdKey, cwd)

function asRecord(v: unknown): AnyRecord {
  return v !== null && typeof v === 'object' ? (v as AnyRecord) : {}
}

const payload = computed<AnyRecord>(() => asRecord(detail.value?.payload))

// -- tabs -------------------------------------------------------------------

const activeTab = ref<TabId>('summary')

// Changing event keeps the current tab (e.g. Delta, to compare consecutive
// round trips); it only resets to Summary if the tab doesn't exist for the
// new event type (e.g. from round_trip to hook).
watch(
  () => [spy.selectedEventId, detail.value?.kind] as const,
  () => {
    if (!detail.value) return
    if (!tabs.value.some((t) => t.id === activeTab.value)) activeTab.value = 'summary'
  }
)

/** Icon shown for each tab; the label becomes a hover tooltip instead of on-button text. */
const TAB_ICON: Record<TabId, string> = {
  summary: '☰',
  request: '↑',
  response: '↓',
  delta: '±',
  call: '⇄',
  json: '{ }',
}

function withIcons(list: { id: TabId; label: string }[]): { id: TabId; label: string; icon: string }[] {
  return list.map((t) => ({ ...t, icon: TAB_ICON[t.id] }))
}

const tabs = computed<{ id: TabId; label: string; icon: string }[]>(() => {
  const kind = detail.value?.kind
  if (kind === 'round_trip') {
    return withIcons([
      { id: 'summary', label: 'Summary' },
      { id: 'request', label: 'Request' },
      { id: 'response', label: 'Response' },
      { id: 'delta', label: 'Delta' },
      { id: 'json', label: 'JSON' },
    ])
  }
  if (kind === 'mcp') {
    return withIcons([
      { id: 'summary', label: 'Summary' },
      { id: 'call', label: 'Call' },
      { id: 'json', label: 'JSON' },
    ])
  }
  return withIcons([
    { id: 'summary', label: 'Summary' },
    { id: 'json', label: 'JSON' },
  ])
})

// -- summary -----------------------------------------------------------------

const rawUsage = computed<AnyRecord>(() => asRecord(payload.value.response).usage ?? {})

/**
 * Token distribution for the Summary donut: the four usage buckets as pie
 * slices plus the share of the input context that came from cache. Colours are
 * theme tokens (no hardcoded dark), so the donut follows light/dark like the
 * dashboard charts.
 */
const usageDonut = computed(() => {
  const u = detail.value?.usage
  if (!u || detail.value?.kind !== 'round_trip') return null
  const slices = [
    { key: 'cache_read', label: 'cache_read', value: u.cache_read_tokens, color: 'var(--c-user)' },
    { key: 'cache_write', label: 'cache_write', value: u.cache_write_tokens, color: 'var(--c-assistant)' },
    { key: 'input', label: 'new input', value: u.input_tokens, color: 'var(--c-llm)' },
    { key: 'output', label: 'output', value: u.output_tokens, color: 'var(--c-tool)' },
  ]
  const total = slices.reduce((s, x) => s + Math.max(0, x.value), 0)
  if (total <= 0) return null
  let acc = 0
  const stops: string[] = []
  for (const s of slices) {
    const start = (acc / total) * 100
    acc += Math.max(0, s.value)
    const end = (acc / total) * 100
    stops.push(`${s.color} ${start}% ${end}%`)
  }
  const inputContext = u.input_tokens + u.cache_read_tokens + u.cache_write_tokens
  const cachePct = inputContext > 0 ? Math.round((u.cache_read_tokens / inputContext) * 100) : 0
  return {
    gradient: `conic-gradient(${stops.join(', ')})`,
    slices: slices.map((s) => ({ ...s, value: Math.max(0, s.value) })),
    cachePct,
  }
})

/** Position of this round trip among the round trips of the same turn (n/total), for the header badge. */
const roundTripPosition = computed<{ index: number; total: number } | null>(() => {
  const d = detail.value
  if (!d || d.kind !== 'round_trip' || d.turn_index == null) return null
  const sameTurn = spy.events.filter(
    (e) => e.kind === 'round_trip' && e.session_id === d.session_id && e.turn_index === d.turn_index
  )
  const idx = sameTurn.findIndex((e) => e.id === d.id)
  if (idx === -1) return null
  return { index: idx + 1, total: sameTurn.length }
})

/** Main hook payload fields, excluding those already shown in the header. */
const hookFields = computed<[string, unknown][]>(() => {
  if (detail.value?.kind !== 'hook') return []
  return Object.entries(payload.value).filter(([k]) => k !== 'tag' && k !== 'hook_event_name')
})

function isPrimitive(v: unknown): boolean {
  return v === null || (typeof v !== 'object' && !Array.isArray(v))
}

// -- request -----------------------------------------------------------------

const requestBody = computed<AnyRecord>(() => asRecord(payload.value.request).body)

const systemBlocks = computed<{ text: string }[]>(() => {
  const s = requestBody.value.system
  if (!s) return []
  if (typeof s === 'string') return [{ text: s }]
  if (Array.isArray(s)) return s.map((b) => ({ text: String(b?.text ?? '') }))
  return []
})

const tools = computed<AnyRecord[]>(() => requestBody.value.tools ?? [])
const messages = computed<AnyRecord[]>(() => requestBody.value.messages ?? [])

// -- response -----------------------------------------------------------------

const response = computed<AnyRecord>(() => payload.value.response ?? {})
const responseMessage = computed<AnyRecord>(() => asRecord(response.value.message ?? response.value.body))
const responseContent = computed<AnyRecord[]>(() =>
  Array.isArray(responseMessage.value.content) ? responseMessage.value.content : []
)

// -- delta ---------------------------------------------------------------------

const prevDetailCache = ref<Record<number, EventDetail>>({})
const prevLoading = ref(false)
const prevError = ref(false)

/** Previous round trip of the same session, by ts_start. */
const previousEvent = computed<EventSummary | null>(() => {
  const d = detail.value
  if (!d || d.kind !== 'round_trip') return null
  const candidates = spy.events.filter(
    (e) =>
      e.kind === 'round_trip' &&
      e.session_id === d.session_id &&
      e.id !== d.id &&
      (e.ts_start ?? 0) < (d.ts_start ?? 0)
  )
  if (candidates.length === 0) return null
  return candidates.reduce((a, b) => ((b.ts_start ?? 0) > (a.ts_start ?? 0) ? b : a))
})

/** Fetch the previous round trip's detail; extracted so the Delta tab's retry
 *  button can re-run it (clearing prevError alone wouldn't re-trigger the watch). */
function loadPrev() {
  const evt = previousEvent.value
  if (!evt || prevDetailCache.value[evt.id]) return
  prevError.value = false
  prevLoading.value = true
  fetchEventDetail(evt.id)
    .then((d) => {
      prevDetailCache.value = { ...prevDetailCache.value, [evt.id]: d }
    })
    .catch(() => {
      prevError.value = true
    })
    .finally(() => {
      prevLoading.value = false
    })
}

watchEffect(() => {
  if (activeTab.value !== 'delta' || !previousEvent.value) return
  loadPrev()
})

const previousDetail = computed<EventDetail | null>(() =>
  previousEvent.value ? (prevDetailCache.value[previousEvent.value.id] ?? null) : null
)

function reqBodyOf(d: EventDetail | null): AnyRecord {
  return asRecord(asRecord(d?.payload).request).body ?? {}
}

function analysisOf(d: EventDetail | null): AnyRecord {
  return asRecord(asRecord(d?.payload).request).analysis ?? {}
}

const addedMessages = computed<AnyRecord[]>(() => {
  if (!previousDetail.value) return []
  const cur = reqBodyOf(detail.value).messages ?? []
  const prev = reqBodyOf(previousDetail.value).messages ?? []
  return cur.slice(prev.length)
})

const tokenDelta = computed(() => {
  if (!previousDetail.value || !detail.value) return null
  const cur = detail.value.usage
  const prev = previousDetail.value.usage
  return {
    input: cur.input_tokens - prev.input_tokens,
    output: cur.output_tokens - prev.output_tokens,
    cache_read: cur.cache_read_tokens - prev.cache_read_tokens,
    cache_write: cur.cache_write_tokens - prev.cache_write_tokens,
  }
})

const charDelta = computed(() => {
  if (!previousDetail.value) return null
  const cur = analysisOf(detail.value)
  const prev = analysisOf(previousDetail.value)
  return {
    system: (cur.system_chars ?? 0) - (prev.system_chars ?? 0),
    tools: (cur.tools?.chars ?? 0) - (prev.tools?.chars ?? 0),
    messages: (cur.messages?.chars ?? 0) - (prev.messages?.chars ?? 0),
  }
})

function fmtDelta(n: number | null | undefined): string {
  if (n == null) return '—'
  const s = formatTokens(n)
  return n > 0 ? `+${s}` : s
}

// -- call (mcp) --------------------------------------------------------------

const mcpParams = computed(() => payload.value.params)
const mcpResult = computed(() => payload.value.result)
const mcpError = computed(() => payload.value.error)

// -- json ----------------------------------------------------------------------

const copied = ref(false)

/** Retry the detail fetch for the selected event (cache miss on error → refetch). */
function retryDetail() {
  if (spy.selectedEventId != null) void spy.select(spy.selectedEventId)
}

async function copyJson() {
  if (!detail.value) return
  try {
    await navigator.clipboard.writeText(JSON.stringify(detail.value.payload, null, 2))
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1500)
  } catch {
    // clipboard unavailable (e.g. insecure context): fail silently
  }
}
</script>

<template>
  <div class="detail-panel">
    <p v-if="spy.selectedEventId == null" class="placeholder">No event selected</p>
    <div v-else-if="spy.detailLoading" class="spinner-wrap">
      <span class="spinner"></span>
      loading detail…
    </div>
    <div v-else-if="spy.detailError || !detail" class="error-retry">
      <p>Failed to load event detail.</p>
      <button class="retry-btn" @click="retryDetail">Retry</button>
    </div>
    <template v-else>
      <header class="header">
        <div class="title-row">
          <template v-if="roundTripPosition">
            <span class="kind-title">round trip</span>
            <span class="rt-pill">#{{ roundTripPosition.index }}/{{ roundTripPosition.total }}</span>
          </template>
          <template v-else>
            <span class="kind-badge" :class="detail.kind">{{ detail.kind }}</span>
            <span v-if="detail.subkind" class="subkind">{{ detail.subkind }}</span>
          </template>
          <button class="close-btn" title="close" @click="spy.clearSelection()">✕</button>
        </div>
        <div class="meta-row">
          <span v-if="detail.turn_index != null">turn {{ detail.turn_index }}</span>
          <span>{{ formatTime(detail.ts_start) }}</span>
          <span>{{ formatDuration(detail.duration_s) }}</span>
          <label v-if="detail.kind === 'round_trip'" class="compact-toggle" title="collapse system-reminder sections">
            <input type="checkbox" v-model="compactView" />
            <span>compact view</span>
          </label>
        </div>
      </header>

      <nav class="tabs">
        <button
          v-for="t in tabs"
          :key="t.id"
          :class="{ active: activeTab === t.id }"
          :title="t.label"
          @click="activeTab = t.id"
        >
          {{ t.icon }}
        </button>
      </nav>

      <div class="tab-content">
        <!-- SUMMARY -->
        <section v-if="activeTab === 'summary'" class="tab-summary">
          <template v-if="detail.kind === 'round_trip'">
            <table class="kv">
              <tbody>
                <tr>
                  <td>model</td>
                  <td>{{ detail.model ?? '—' }}</td>
                </tr>
                <tr>
                  <td>status</td>
                  <td>{{ detail.status ?? '—' }}</td>
                </tr>
                <tr>
                  <td>stop_reason</td>
                  <td>{{ detail.stop_reason ?? '—' }}</td>
                </tr>
                <tr>
                  <td>ttfb</td>
                  <td>{{ formatDuration(detail.ttfb_s) }}</td>
                </tr>
                <tr>
                  <td>total duration</td>
                  <td>{{ formatDuration(detail.duration_s) }}</td>
                </tr>
              </tbody>
            </table>

            <div class="section-title">Token distribution</div>
            <div v-if="usageDonut" class="donut-block">
              <div class="donut-wrap">
                <div class="donut" :style="{ background: usageDonut.gradient }"></div>
                <div class="donut-hole">
                  <b>{{ usageDonut.cachePct }}%</b>
                  <span>from cache</span>
                </div>
              </div>
              <ul class="donut-legend">
                <li v-for="s in usageDonut.slices" :key="s.key">
                  <i class="swatch" :style="{ backgroundColor: s.color }"></i>
                  <span class="dl-label">{{ s.label }}</span>
                  <b>{{ formatTokens(s.value) }}</b>
                </li>
              </ul>
            </div>
            <p v-else class="placeholder">no token usage recorded</p>
            <p v-if="usageDonut" class="donut-note">
              Most of the context comes from <b>cache</b> (already-seen tokens), not new input — that
              is why long round trips stay cheap and fast.
            </p>

            <div class="section-title">Full usage (raw API)</div>
            <JsonTree :value="rawUsage" />

            <div v-if="detail.tool_names.length" class="section-title">Tools called</div>
            <div v-if="detail.tool_names.length" class="chips">
              <span v-for="name in detail.tool_names" :key="name" class="chip">{{ name }}</span>
            </div>
          </template>

          <template v-else-if="detail.kind === 'hook'">
            <table class="kv">
              <tbody>
                <tr>
                  <td>hook_event_name</td>
                  <td>{{ detail.subkind ?? '—' }}</td>
                </tr>
                <tr>
                  <td>session_id</td>
                  <td>{{ detail.session_id ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
            <div class="section-title">Payload fields</div>
            <table class="kv">
              <tbody>
                <tr v-for="[k, v] in hookFields" :key="k">
                  <td>{{ k }}</td>
                  <td>
                    <span v-if="isPrimitive(v)">{{ v }}</span>
                    <JsonTree v-else :value="v" />
                  </td>
                </tr>
              </tbody>
            </table>
          </template>

          <template v-else-if="detail.kind === 'mcp'">
            <table class="kv">
              <tbody>
                <tr>
                  <td>method</td>
                  <td>{{ payload.method ?? detail.subkind ?? '—' }}</td>
                </tr>
                <tr>
                  <td>server</td>
                  <td>{{ payload.server_name ?? '—' }}</td>
                </tr>
                <tr>
                  <td>rpc_id</td>
                  <td>{{ payload.rpc_id ?? '—' }}</td>
                </tr>
                <tr>
                  <td>duration</td>
                  <td>{{ formatDuration(detail.duration_s) }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </section>

        <!-- REQUEST (round_trip only) -->
        <section v-else-if="activeTab === 'request'" class="tab-request">
          <div class="section-title">System (request field)</div>
          <p v-if="systemBlocks.length === 0" class="placeholder">no system prompt</p>
          <Collapsible
            v-for="(b, i) in systemBlocks"
            :key="i"
            :title="systemBlocks.length > 1 ? `block ${i + 1}/${systemBlocks.length}` : 'system'"
            :meta="`${b.text.length.toLocaleString('en-US')} characters`"
          >
            <pre class="pre-wrap">{{ b.text }}</pre>
          </Collapsible>

          <div class="section-title">Tools ({{ tools.length }})</div>
          <p v-if="tools.length === 0" class="placeholder">no tools available</p>
          <Collapsible
            v-for="(t, i) in tools"
            :key="i"
            :title="t.name ?? `tool ${i}`"
            :meta="`schema ${JSON.stringify(t.input_schema ?? {}).length.toLocaleString('en-US')} chars`"
          >
            <p class="pre-wrap">{{ t.description ?? '(no description)' }}</p>
            <div class="label">input_schema</div>
            <JsonTree :value="t.input_schema" />
          </Collapsible>

          <div class="section-title">Messages ({{ messages.length }})</div>
          <MessageBlock v-for="(m, i) in messages" :key="i" :message="m" collapsible />
        </section>

        <!-- RESPONSE (round_trip only) -->
        <section v-else-if="activeTab === 'response'" class="tab-response">
          <div v-if="response.error" class="error-box">
            Error: {{ response.error }}
          </div>
          <template v-else>
            <p v-if="responseContent.length === 0" class="placeholder">no content</p>
            <ContentBlock v-for="(b, i) in responseContent" :key="i" :block="b" />
            <div class="section-title">Usage &amp; stop</div>
            <table class="kv">
              <tbody>
                <tr>
                  <td>stop_reason</td>
                  <td>{{ response.stop_reason ?? detail.stop_reason ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
            <JsonTree :value="response.usage ?? {}" />
          </template>
        </section>

        <!-- DELTA (round_trip only) -->
        <section v-else-if="activeTab === 'delta'" class="tab-delta">
          <p v-if="!previousEvent" class="placeholder">
            First request of the conversation — all context is new.
          </p>
          <div v-else-if="prevLoading" class="spinner-wrap">
            <span class="spinner"></span>
            loading previous round trip…
          </div>
          <div v-else-if="prevError || !previousDetail" class="error-retry">
            <p>Failed to load the previous round trip.</p>
            <button class="retry-btn" @click="loadPrev">Retry</button>
          </div>
          <template v-else>
            <div class="section-title">Differences from the previous round trip</div>
            <table class="kv delta">
              <tbody>
                <tr>
                  <td>input (new)</td>
                  <td>{{ fmtDelta(tokenDelta?.input) }}</td>
                </tr>
                <tr>
                  <td>cache_read</td>
                  <td>{{ fmtDelta(tokenDelta?.cache_read) }}</td>
                </tr>
                <tr>
                  <td>cache_write</td>
                  <td>{{ fmtDelta(tokenDelta?.cache_write) }}</td>
                </tr>
                <tr>
                  <td>output</td>
                  <td>{{ fmtDelta(tokenDelta?.output) }}</td>
                </tr>
                <tr>
                  <td>system_chars</td>
                  <td>{{ fmtDelta(charDelta?.system) }}</td>
                </tr>
                <tr>
                  <td>tools_chars</td>
                  <td>{{ fmtDelta(charDelta?.tools) }}</td>
                </tr>
                <tr>
                  <td>messages_chars</td>
                  <td>{{ fmtDelta(charDelta?.messages) }}</td>
                </tr>
              </tbody>
            </table>

            <div class="section-title">Added messages ({{ addedMessages.length }})</div>
            <p v-if="addedMessages.length === 0" class="placeholder">
              no new messages compared to the previous round trip
            </p>
            <MessageBlock v-for="(m, i) in addedMessages" :key="i" :message="m" />
          </template>
        </section>

        <!-- CALL (mcp only) -->
        <section v-else-if="activeTab === 'call'" class="tab-call">
          <div v-if="mcpError" class="error-box">Error: <JsonTree :value="mcpError" /></div>
          <div class="section-title">Params</div>
          <JsonTree :value="mcpParams ?? {}" />
          <div class="section-title">Result</div>
          <p v-if="mcpResult === undefined" class="placeholder">no result (pending or failed)</p>
          <JsonTree v-else :value="mcpResult" />
        </section>

        <!-- raw JSON -->
        <section v-else-if="activeTab === 'json'" class="tab-json">
          <button class="copy-btn" @click="copyJson">{{ copied ? 'copied!' : 'copy' }}</button>
          <JsonTree :value="detail.payload" />
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.detail-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.placeholder {
  color: var(--muted);
  font-style: italic;
  padding: 1rem;
}

.hint {
  color: var(--muted);
  font-size: 0.82em;
  margin: 0 0 8px;
  line-height: 1.4;
}
.hint code {
  font-family: var(--mono, monospace);
  background: var(--surface, #f0f0f0);
  padding: 0 3px;
  border-radius: 3px;
}

.spinner-wrap {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 1.5rem 1rem;
  color: var(--muted);
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.header {
  padding: 0.75rem 1rem 0.5rem;
  border-bottom: 1px solid var(--border);
}

.title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* round-trip header (see the "Direzioni Leggibilità" design, Image 5):
   a plain "ROUND TRIP" heading plus a green filled pill for its position. */
.kind-title {
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text);
}

.rt-pill {
  font: 700 0.68rem 'JetBrains Mono', ui-monospace, monospace;
  color: #fff;
  background-color: var(--c-llm);
  padding: 0.1rem 0.5rem;
  border-radius: 99px;
}

.kind-badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  background-color: var(--panel-alt);
  color: var(--accent);
}

.kind-badge.hook {
  color: var(--accent-live);
}

.kind-badge.mcp {
  color: var(--c-assistant);
}

.subkind {
  font-size: 0.8rem;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.close-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--muted);
  font-size: 1rem;
  cursor: pointer;
  line-height: 1;
  padding: 0.2rem 0.3rem;
}

.close-btn:hover {
  color: var(--danger);
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin-top: 0.35rem;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 0.72rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.compact-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-left: auto;
  cursor: pointer;
  user-select: none;
}

.compact-toggle input {
  cursor: pointer;
  accent-color: var(--accent);
}

/* the segmented tab bar sits on a subtle filled track so the container reads
   as a group (see design Image 7). --panel would match the surrounding panel
   and vanish, so use --border, one step darker. */
.tabs {
  display: flex;
  gap: 4px;
  margin: 0.6rem 0.75rem;
  background-color: var(--border);
  border-radius: 9px;
  padding: 4px;
  overflow-x: auto;
}

.tabs button {
  flex: 1;
  background: none;
  border: none;
  border-radius: 6px;
  color: var(--muted);
  padding: 0.4rem 0.5rem;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  text-align: center;
}

.tabs button:hover {
  color: var(--text);
}

.tabs button.active {
  color: var(--text);
  background-color: var(--panel-alt);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem 1rem 1.5rem;
}

.section-title {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--muted-faint);
  margin: 0.9rem 0 0.4rem;
}

.section-title:first-child {
  margin-top: 0;
}

.label {
  font-size: 0.72rem;
  color: var(--muted);
  margin: 0.3rem 0 0.15rem;
}

.kv {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

.kv td {
  padding: 0.2rem 0.4rem 0.2rem 0;
  vertical-align: top;
}

.kv td:first-child {
  color: var(--muted);
  white-space: nowrap;
  width: 1%;
}

.kv.delta td:last-child {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

/* -- token-distribution donut (Summary) -- */
.donut-block {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.donut-wrap {
  position: relative;
  width: 92px;
  height: 92px;
  flex: none;
}

.donut {
  width: 92px;
  height: 92px;
  border-radius: 50%;
}

.donut-hole {
  position: absolute;
  inset: 15px;
  border-radius: 50%;
  background-color: var(--panel);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.donut-hole b {
  font-size: 0.95rem;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.donut-hole span {
  font-size: 0.58rem;
  color: var(--muted-faint);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.donut-legend {
  list-style: none;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.donut-legend li {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--muted);
}

.donut-legend .swatch {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  flex: none;
}

.donut-legend .dl-label {
  flex: 1;
  min-width: 0;
}

.donut-legend b {
  color: var(--text);
  font-variant-numeric: tabular-nums;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 0.72rem;
}

.donut-note {
  font-size: 0.75rem;
  line-height: 1.45;
  color: var(--muted);
  margin-top: 0.6rem;
}

.donut-note b {
  color: var(--text);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.chip {
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0.1rem 0.45rem;
  font-size: 0.75rem;
}

.pre-wrap {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: inherit;
  font-size: 0.85rem;
}

.error-box {
  background-color: rgba(224, 87, 74, 0.12);
  border: 1px solid var(--danger);
  color: var(--danger);
  border-radius: 4px;
  padding: 0.5rem 0.6rem;
  margin-bottom: 0.6rem;
  font-size: 0.82rem;
}

.error-retry {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 1.5rem 1rem;
  color: var(--muted);
  font-size: 0.85rem;
}

.retry-btn {
  background-color: var(--panel-alt);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.3rem 0.8rem;
  font-size: 0.8rem;
  cursor: pointer;
}

.retry-btn:hover {
  border-color: var(--accent);
}

.copy-btn {
  background-color: var(--panel-alt);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.25rem 0.6rem;
  font-size: 0.75rem;
  cursor: pointer;
  margin-bottom: 0.6rem;
}

.copy-btn:hover {
  border-color: var(--accent);
}
</style>
