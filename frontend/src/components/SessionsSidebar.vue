<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSpyStore, type SessionNode } from '../stores/spy'
import { useTheme } from '../composables/useTheme'
import { formatTokens } from '../utils/format'
import type { Session } from '../types'

const spy = useSpyStore()
const router = useRouter()
const route = useRoute()
const { theme, setTheme } = useTheme()

interface FlatRow {
  session: SessionNode
  depth: number
}

function flatten(nodes: SessionNode[], depth: number): FlatRow[] {
  const rows: FlatRow[] = []
  for (const n of nodes) {
    rows.push({ session: n, depth })
    rows.push(...flatten(n.children, depth + 1))
  }
  return rows
}

const rows = computed(() => flatten(spy.sessionTree, 0))

// -- selection / delete mode -----------------------------------------------
const selectionMode = ref(false)
/** explicitly checked ids (the roots of the selection). */
const selected = ref<Set<string>>(new Set())

/** true if an ancestor session is already selected: this row is then covered
 * by the cascade and its checkbox is checked but locked. */
function coveredByAncestor(id: string): boolean {
  let parent = spy.sessions[id]?.parent_session_id ?? null
  while (parent) {
    if (selected.value.has(parent)) return true
    parent = spy.sessions[parent]?.parent_session_id ?? null
  }
  return false
}

function isChecked(id: string): boolean {
  return selected.value.has(id) || coveredByAncestor(id)
}

function isLocked(id: string): boolean {
  return coveredByAncestor(id)
}

/** all ids that will disappear (checked roots + visible checked descendants). */
const effectiveIds = computed(() => rows.value.map((r) => r.session.id).filter(isChecked))

function toggleSelectionMode() {
  selectionMode.value = !selectionMode.value
  if (!selectionMode.value) selected.value = new Set()
}

function toggleRow(id: string) {
  if (isLocked(id)) return
  const next = new Set(selected.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
    // drop explicit selections of descendants now made redundant.
    for (const other of [...next]) {
      if (other !== id && hasAncestor(other, id)) next.delete(other)
    }
  }
  selected.value = next
}

/** true if `ancestor` is an ancestor of `id` walking up the parent chain. */
function hasAncestor(id: string, ancestor: string): boolean {
  let parent = spy.sessions[id]?.parent_session_id ?? null
  while (parent) {
    if (parent === ancestor) return true
    parent = spy.sessions[parent]?.parent_session_id ?? null
  }
  return false
}

function cancelSelection() {
  selectionMode.value = false
  selected.value = new Set()
}

/** ids of the top-level sessions (children follow in cascade). */
const topLevelIds = computed(() =>
  rows.value.filter((r) => r.depth === 0).map((r) => r.session.id)
)

const allSelected = computed(
  () => topLevelIds.value.length > 0 && topLevelIds.value.every((id) => selected.value.has(id))
)

/** Select all top-level sessions (typical case: delete everything except a
 * few to keep, unchecked afterwards). If all are already selected, clears. */
function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(topLevelIds.value)
}

async function confirmDelete() {
  const ids = effectiveIds.value
  if (ids.length === 0) return
  const plural = ids.length === 1 ? 'the selected session' : `${ids.length} selected sessions`
  const msg =
    `Delete ${plural}? Any child sessions (sub-agents) and all their events ` +
    `will be removed in cascade. This cannot be undone.`
  if (!window.confirm(msg)) return
  const currentDeleted = spy.currentSessionId != null && ids.includes(spy.currentSessionId)
  try {
    await spy.deleteSessions(ids)
  } catch (err) {
    window.alert(
      `Delete failed: ${err instanceof Error ? err.message : err}.\n` +
        `If the collector was started with an older version of the code, restart it.`
    )
    return
  }
  cancelSelection()
  if (currentDeleted) router.push('/')
}

/** Shortened model name to avoid crowding the row (e.g. claude-sonnet-4-5-20250929 -> sonnet-4.5). */
function abbreviateModel(model: string | null): string {
  if (!model) return '—'
  const m = model.match(/claude-([a-z]+)-(\d+)(?:-(\d+))?/)
  if (m) {
    const [, family, major, minor] = m
    return minor ? `${family}-${major}.${minor}` : `${family}-${major}`
  }
  return model.length > 16 ? `${model.slice(0, 16)}…` : model
}

/** Stable chip color derived from the tag name (simple hash). */
function tagColor(tag: string): string {
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) >>> 0
  const hue = hash % 360
  return `hsl(${hue}, 55%, 45%)`
}

function totalTokens(s: Session): number {
  const u = s.usage_incl_children
  return u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
}

const onDashboard = computed(() => route.path === '/')

/** Highlighted row: on the dashboard it's the featured session, elsewhere the open one. */
function isActiveRow(id: string): boolean {
  if (selectionMode.value) return false
  if (onDashboard.value) return id === spy.featuredSessionId
  return id === spy.currentSessionId
}

function onRowClick(id: string) {
  if (selectionMode.value) {
    toggleRow(id)
    return
  }
  // On the dashboard a click doesn't navigate: it just features the clicked
  // session (even a sub-agent: the charts then show its round trips).
  if (onDashboard.value) {
    spy.featuredSessionId = id
    return
  }
  router.push(`/session/${id}`)
}

function externalHref(id: string): string {
  return `/ui/session/${id}`
}

// -- settings popover (theme) -------------------------------------------------
const settingsOpen = ref(false)
const helpOpen = ref(false)
</script>

<template>
  <nav class="sessions-sidebar">
    <div class="toolbar">
      <button
        type="button"
        class="edit-toggle"
        :class="{ active: selectionMode }"
        :title="selectionMode ? 'exit selection mode' : 'select sessions to delete'"
        @click="toggleSelectionMode"
      >
        🗑
      </button>
    </div>

    <div class="list">
      <p v-if="rows.length === 0" class="empty">No sessions</p>
      <div
        v-for="row in rows"
        :key="row.session.id"
        class="row"
        :class="{
          active: isActiveRow(row.session.id),
          selecting: selectionMode,
          checked: selectionMode && isChecked(row.session.id),
        }"
        :style="{ paddingLeft: `${0.6 + row.depth * 1}rem` }"
        @click="onRowClick(row.session.id)"
      >
        <input
          v-if="selectionMode"
          type="checkbox"
          class="check"
          :checked="isChecked(row.session.id)"
          :disabled="isLocked(row.session.id)"
          :title="isLocked(row.session.id) ? 'deleted in cascade with its parent' : ''"
        />
        <!-- Left gutter (connector + dot) kept out of the text column so that
             both lines align with the name/tag, not with the dot. -->
        <div class="gutter">
          <span v-if="row.depth > 0" class="connector">↳</span>
          <span class="dot"></span>
        </div>
        <div class="row-lines">
          <div class="line1">
            <span v-if="row.session.tag" class="chip" :style="{ backgroundColor: tagColor(row.session.tag) }">
              {{ row.session.tag }}
            </span>
            <!-- The raw session id is dropped: the tag already identifies the
                 row. Only a real, human-readable title is shown as the name. -->
            <span v-if="row.session.title" class="title">{{ row.session.title }}</span>
            <!-- The round-trip count doubles as the run-state signal: vivid
                 while the session is still running, muted once Stop arrived. -->
            <span
              class="rt"
              :class="{ stopped: !row.session.live }"
              :title="`${row.session.round_trips} round trips${row.session.live ? '' : ' · ended'}`"
            >
              {{ row.session.round_trips }}
            </span>
          </div>
          <div class="line2">
            <span class="model">{{ abbreviateModel(row.session.model) }}</span>
            <span class="tokens">{{ formatTokens(totalTokens(row.session)) }}</span>
            <span v-if="!selectionMode && spy.unseenCounts[row.session.id]" class="badge">
              {{ spy.unseenCounts[row.session.id] }}
            </span>
            <a
              v-if="!selectionMode"
              class="external"
              :href="externalHref(row.session.id)"
              target="_blank"
              rel="noopener"
              title="open in another tab"
              @click.stop
            >
              ↗
            </a>
          </div>
        </div>
      </div>
    </div>

    <div v-if="selectionMode" class="delete-bar">
      <button type="button" class="cancel-btn" @click="toggleAll">
        {{ allSelected ? 'Select none' : 'Select all' }}
      </button>
      <button
        type="button"
        class="delete-btn"
        :disabled="effectiveIds.length === 0"
        @click="confirmDelete"
      >
        Delete {{ effectiveIds.length }}
        {{ effectiveIds.length === 1 ? 'session' : 'sessions' }}
      </button>
    </div>

    <div class="footer">
      <div v-if="settingsOpen" class="settings-panel">
        <div class="settings-title">Customize</div>
        <div class="settings-row">
          <span>Theme</span>
          <div class="theme-toggle">
            <button
              class="theme-opt"
              :class="{ active: theme === 'light' }"
              @click="setTheme('light')"
            >
              ☀️ Light
            </button>
            <button class="theme-opt" :class="{ active: theme === 'dark' }" @click="setTheme('dark')">
              🌙 Dark
            </button>
          </div>
        </div>
        <div class="settings-hint">More customization options will land here.</div>
      </div>
      <div class="footer-row">
        <button
          type="button"
          class="help-btn"
          title="Quick start / help"
          @click="helpOpen = true"
        >
          ?
        </button>
        <button type="button" class="settings-btn" @click="settingsOpen = !settingsOpen">
          <span class="settings-ic">⚙️</span>Customize
        </button>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="helpOpen" class="help-overlay" @click.self="helpOpen = false">
        <div class="help-modal">
          <header class="help-header">
            <span class="help-title">Quick start</span>
            <button type="button" class="help-close" title="close" @click="helpOpen = false">✕</button>
          </header>
          <div class="help-body">
            <ol>
              <li>Avvia il collector:<br /><code>cd server &amp;&amp; uv run agentspy</code></li>
              <li>
                Fai passare Claude Code dal proxy:<br />
                <code>ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude</code>
              </li>
              <li>
                Per taggare una raccolta (separare run diverse):<br />
                <code>ANTHROPIC_CUSTOM_HEADERS="x-agentspy-tag: my-tag" claude</code>
              </li>
            </ol>
          </div>
        </div>
      </div>
    </Teleport>
  </nav>
</template>

<style scoped>
.sessions-sidebar {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.toolbar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--border);
}

.edit-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
}

.edit-toggle:hover {
  color: var(--text);
  border-color: var(--muted);
}

.edit-toggle.active {
  color: #fff;
  background-color: var(--danger);
  border-color: var(--danger);
}

.list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  padding: 0.4rem 0;
}

.empty {
  padding: 0.75rem 1rem;
  color: var(--muted);
  font-style: italic;
  font-size: 0.85rem;
}

.check {
  flex: none;
  margin: 0.15rem 0 0;
  accent-color: var(--danger);
  /* the row handles the click: the checkbox is just a visual indicator. */
  pointer-events: none;
}

.row.selecting {
  cursor: pointer;
}

.row.checked {
  background-color: rgba(224, 87, 74, 0.12);
}

.row.checked:hover {
  background-color: rgba(224, 87, 74, 0.18);
}

.delete-bar {
  flex: none;
  display: flex;
  gap: 0.5rem;
  padding: 0.5rem;
  border-top: 1px solid var(--border);
  background-color: var(--panel-alt);
}

.delete-btn {
  flex: 1;
  background: transparent;
  border: 1px solid var(--danger);
  color: var(--danger);
  border-radius: 4px;
  padding: 0.35rem 0.5rem;
  font-size: 0.78rem;
  cursor: pointer;
}

.delete-btn:hover:not(:disabled) {
  background-color: var(--danger);
  color: #fff;
}

.delete-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.cancel-btn {
  flex: none;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 4px;
  padding: 0.35rem 0.6rem;
  font-size: 0.78rem;
  cursor: pointer;
}

.cancel-btn:hover {
  color: var(--text);
  border-color: var(--muted);
}

.row {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  padding: 0.35rem 0.6rem;
  cursor: pointer;
  font-size: 0.75rem;
  border-left: 3px solid transparent;
  border-radius: 0 8px 8px 0;
}

.row:hover {
  background-color: var(--panel-alt);
}

/* the session OPEN in the page: tinted background + border, the one
   unambiguous "you are here" signal. */
.row.active {
  background-color: rgba(124, 79, 209, 0.14);
  border-left-color: var(--accent);
  box-shadow: inset 0 0 0 1px rgba(124, 79, 209, 0.3);
}

/* fixed left gutter: connector + dot live here so both text lines start at the
   same x (aligned with the tag/name, not the dot). */
.gutter {
  flex: none;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  height: 1.15rem;
}

.row-lines {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.line1 {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

/* line 2 is pure metadata (model · tokens): quieter and smaller than line 1,
   which now carries the identity (tag + name). */
.line2 {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.connector {
  color: var(--muted-faint);
  font-size: 0.75rem;
}

.dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--muted-faint);
}

.chip {
  flex: none;
  padding: 0.05rem 0.4rem;
  border-radius: 99px;
  font-size: 0.68rem;
  font-weight: 600;
  color: #fff;
}

.title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
  font-size: 0.76rem;
}

/* round-trip count badge next to the name. Its colour carries the run state:
   vivid while running, muted (grey) once the session has ended (Stop received). */
.rt {
  flex: none;
  margin-left: auto;
  background-color: var(--danger);
  color: #fff;
  border-radius: 99px;
  padding: 0 0.4rem;
  font-size: 0.65rem;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.rt.stopped {
  background-color: var(--muted-faint);
}

/* can shrink (with ellipsis) before overflowing the row */
.model {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted-faint);
  font-size: 0.64rem;
}

.tokens {
  flex: none;
  color: var(--muted-faint);
  font-variant-numeric: tabular-nums;
  font-size: 0.64rem;
}

.badge {
  flex: none;
  background-color: var(--accent);
  color: #fff;
  border-radius: 8px;
  padding: 0 0.35rem;
  font-size: 0.65rem;
  line-height: 1.3;
}

.external {
  flex: none;
  margin-left: auto;
  color: var(--muted);
  text-decoration: none;
  padding: 0 0.15rem;
}

.external:hover {
  color: var(--accent);
}

.footer {
  flex: none;
  border-top: 1px solid var(--border);
  padding: 0.5rem;
  position: relative;
}

.footer-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.settings-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  background: transparent;
  border: none;
  padding: 0.45rem 0.4rem;
  border-radius: 7px;
  cursor: pointer;
  font: 600 0.78rem 'Inter', sans-serif;
  color: var(--muted);
}

.settings-btn:hover {
  background-color: var(--panel-alt);
}

.help-btn {
  flex: none;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background-color: var(--panel-alt);
  color: var(--muted);
  font: 700 0.9rem 'Inter', sans-serif;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.help-btn:hover {
  border-color: var(--accent);
  color: var(--text);
}

/* -- help modal (quick start) -- */
.help-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  z-index: 1000;
}

.help-modal {
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  width: 100%;
  max-width: 560px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.help-header {
  display: flex;
  align-items: center;
  padding: 0.7rem 1rem;
  border-bottom: 1px solid var(--border);
}

.help-title {
  font-weight: 700;
  color: var(--text);
}

.help-close {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--muted);
  font-size: 1rem;
  cursor: pointer;
  line-height: 1;
  padding: 0.1rem 0.3rem;
}

.help-close:hover {
  color: var(--danger);
}

.help-body {
  padding: 0.9rem 1rem 1.1rem;
}

.help-body ol {
  padding-left: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  color: var(--text);
  font-size: 0.85rem;
}

.help-body code {
  display: inline-block;
  margin-top: 0.25rem;
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  padding: 0.2rem 0.45rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}

.settings-ic {
  font-size: 0.95rem;
}

.settings-panel {
  position: absolute;
  left: 0.5rem;
  right: 0.5rem;
  bottom: calc(100% + 0.4rem);
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.75rem;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  z-index: 5;
}

.settings-title {
  font: 700 0.65rem system-ui;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted-faint);
  margin-bottom: 0.5rem;
}

.settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  font-size: 0.8rem;
  color: var(--text);
}

.theme-toggle {
  display: flex;
  background-color: var(--border);
  border-radius: 8px;
  padding: 2px;
  gap: 2px;
}

.theme-opt {
  font: 600 0.72rem 'Inter', sans-serif;
  color: var(--muted);
  background: transparent;
  border: none;
  padding: 0.35rem 0.55rem;
  border-radius: 6px;
  cursor: pointer;
}

.theme-opt.active {
  background-color: var(--panel-alt);
  color: var(--text);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.settings-hint {
  font-size: 0.65rem;
  color: var(--muted-faint);
  margin-top: 0.5rem;
}
</style>
