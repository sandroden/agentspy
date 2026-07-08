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

watchEffect(() => {
  const evt = previousEvent.value
  if (activeTab.value !== 'delta' || !evt || prevDetailCache.value[evt.id]) return
  prevLoading.value = true
  fetchEventDetail(evt.id)
    .then((d) => {
      prevDetailCache.value = { ...prevDetailCache.value, [evt.id]: d }
    })
    .finally(() => {
      prevLoading.value = false
    })
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
    <div v-else-if="spy.detailLoading || !detail" class="spinner-wrap">
      <span class="spinner"></span>
      loading detail…
    </div>
    <template v-else>
      <header class="header">
        <div class="title-row">
          <span v-if="roundTripPosition" class="kind-badge round_trip">
            round trip #{{ roundTripPosition.index }}/{{ roundTripPosition.total }}
          </span>
          <span v-else class="kind-badge" :class="detail.kind">{{ detail.kind }}</span>
          <span v-if="detail.subkind" class="subkind">{{ detail.subkind }}</span>
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

            <div class="section-title">Usage</div>
            <table class="kv">
              <tbody>
                <tr>
                  <td>input (new)</td>
                  <td>{{ formatTokens(detail.usage.input_tokens) }}</td>
                </tr>
                <tr>
                  <td>cache_read</td>
                  <td>{{ formatTokens(detail.usage.cache_read_tokens) }}</td>
                </tr>
                <tr>
                  <td>cache_write</td>
                  <td>{{ formatTokens(detail.usage.cache_write_tokens) }}</td>
                </tr>
                <tr>
                  <td>output</td>
                  <td>{{ formatTokens(detail.usage.output_tokens) }}</td>
                </tr>
              </tbody>
            </table>

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
          <div v-else-if="prevLoading || !previousDetail" class="spinner-wrap">
            <span class="spinner"></span>
            loading previous round trip…
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
  margin-top: 0.3rem;
  font-size: 0.75rem;
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

.tabs {
  display: flex;
  gap: 4px;
  margin: 0.6rem 0.75rem;
  background-color: var(--panel);
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
