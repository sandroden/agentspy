<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSpyStore, type SessionNode } from '../stores/spy'
import { formatTokens } from '../utils/format'
import type { Session } from '../types'

const spy = useSpyStore()
const router = useRouter()
const route = useRoute()

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

// -- modalità selezione / eliminazione ------------------------------------
const selectionMode = ref(false)
/** id esplicitamente spuntati (le radici della selezione). */
const selected = ref<Set<string>>(new Set())

/** true se una sessione antenata è già selezionata: allora questa riga è
 * coperta dalla cascata e la sua checkbox è spuntata ma bloccata. */
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

/** tutti gli id che spariranno (radici + discendenti visibili spuntati). */
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
    // rimuove selezioni esplicite di discendenti ora ridondanti.
    for (const other of [...next]) {
      if (other !== id && hasAncestor(other, id)) next.delete(other)
    }
  }
  selected.value = next
}

/** true se `ancestor` è antenato di `id` risalendo la catena dei parent. */
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

/** id delle sessioni top-level (le figlie seguono in cascata). */
const topLevelIds = computed(() =>
  rows.value.filter((r) => r.depth === 0).map((r) => r.session.id)
)

const allSelected = computed(
  () => topLevelIds.value.length > 0 && topLevelIds.value.every((id) => selected.value.has(id))
)

/** Seleziona tutte le top-level (caso tipico: cancellare tutto tranne poche
 * da tenere, che si de-spuntano dopo). Se già tutte selezionate, azzera. */
function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(topLevelIds.value)
}

async function confirmDelete() {
  const ids = effectiveIds.value
  if (ids.length === 0) return
  const plural = ids.length === 1 ? 'la sessione selezionata' : `${ids.length} sessioni selezionate`
  const msg =
    `Eliminare ${plural}? Verranno rimosse in cascata anche le eventuali ` +
    `sessioni figlie (subagenti) e tutti i loro eventi. L'operazione è definitiva.`
  if (!window.confirm(msg)) return
  const currentDeleted = spy.currentSessionId != null && ids.includes(spy.currentSessionId)
  try {
    await spy.deleteSessions(ids)
  } catch (err) {
    window.alert(
      `Eliminazione fallita: ${err instanceof Error ? err.message : err}.\n` +
        `Se il collector è stato avviato con una versione precedente del codice, riavvialo.`
    )
    return
  }
  cancelSelection()
  if (currentDeleted) router.push('/')
}

/** Modello abbreviato per non affollare la riga (es. claude-sonnet-4-5-20250929 -> sonnet-4.5). */
function abbreviateModel(model: string | null): string {
  if (!model) return '—'
  const m = model.match(/claude-([a-z]+)-(\d+)(?:-(\d+))?/)
  if (m) {
    const [, family, major, minor] = m
    return minor ? `${family}-${major}.${minor}` : `${family}-${major}`
  }
  return model.length > 16 ? `${model.slice(0, 16)}…` : model
}

/** Colore chip stabile derivato dal nome del tag (hash semplice). */
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

/** Riga evidenziata: in dashboard è la featured, altrove la sessione aperta. */
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
  // In dashboard il click non naviga: mette in evidenza la sessione cliccata
  // (anche un subagente: i grafici mostrano i suoi round trip).
  if (onDashboard.value) {
    spy.featuredSessionId = id
    return
  }
  router.push(`/session/${id}`)
}

function externalHref(id: string): string {
  return `/ui/session/${id}`
}
</script>

<template>
  <nav class="sessions-sidebar">
    <div class="toolbar">
      <router-link to="/" class="home-link" title="torna alla dashboard con i grafici">
        📊 Dashboard
      </router-link>
      <button
        type="button"
        class="edit-toggle"
        :class="{ active: selectionMode }"
        :title="selectionMode ? 'esci dalla modalità selezione' : 'seleziona sessioni da eliminare'"
        @click="toggleSelectionMode"
      >
        {{ selectionMode ? '✕ Fine' : '🗑 Modifica' }}
      </button>
    </div>

    <div class="list">
      <p v-if="rows.length === 0" class="empty">Nessuna sessione</p>
      <div
        v-for="row in rows"
        :key="row.session.id"
        class="row"
        :class="{
          active: isActiveRow(row.session.id),
          live: row.session.live,
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
          :title="isLocked(row.session.id) ? 'eliminata in cascata col genitore' : ''"
        />
        <span class="dot" :class="{ live: row.session.live }"></span>
        <span v-if="row.session.live" class="live-chip">LIVE</span>
        <span v-if="row.session.tag" class="chip" :style="{ backgroundColor: tagColor(row.session.tag) }">
          {{ row.session.tag }}
        </span>
        <span class="title">{{ row.session.title || row.session.id }}</span>
        <span class="rt" :title="`${row.session.round_trips} round trip`">
          {{ row.session.round_trips }}
        </span>
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
          title="apri in un'altra scheda"
          @click.stop
        >
          ↗
        </a>
      </div>
    </div>

    <div v-if="selectionMode" class="delete-bar">
      <button type="button" class="cancel-btn" @click="toggleAll">
        {{ allSelected ? 'Nessuna' : 'Tutte' }}
      </button>
      <button
        type="button"
        class="delete-btn"
        :disabled="effectiveIds.length === 0"
        @click="confirmDelete"
      >
        Elimina {{ effectiveIds.length }}
        {{ effectiveIds.length === 1 ? 'sessione' : 'sessioni' }}
      </button>
      <button type="button" class="cancel-btn" @click="cancelSelection">Annulla</button>
    </div>
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
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--border);
}

.home-link {
  color: var(--muted);
  text-decoration: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.15rem 0.5rem;
  font-size: 0.72rem;
}

.home-link:hover {
  color: var(--text);
  border-color: var(--muted);
}

/* evidenzia quando la dashboard è la vista corrente */
.home-link.router-link-exact-active {
  color: var(--accent);
  border-color: var(--accent);
}

.edit-toggle {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 4px;
  padding: 0.15rem 0.5rem;
  font-size: 0.72rem;
  cursor: pointer;
}

.edit-toggle:hover {
  color: var(--text);
  border-color: var(--muted);
}

.edit-toggle.active {
  color: var(--danger);
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
  margin: 0;
  accent-color: var(--danger);
  /* il click è gestito dalla riga: la checkbox è solo un indicatore visuale. */
  pointer-events: none;
}

.row.selecting {
  cursor: pointer;
}

.row.checked {
  background-color: rgba(229, 83, 75, 0.12);
}

.row.checked:hover {
  background-color: rgba(229, 83, 75, 0.18);
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
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.6rem;
  cursor: pointer;
  font-size: 0.8rem;
  border-left: 2px solid transparent;
}

.row:hover {
  background-color: var(--panel-alt);
}

.row.active {
  background-color: var(--panel-alt);
  border-left-color: var(--accent);
  border-left-width: 3px;
}

/* live vince sulla selezione: bordo verde + sfondo acceso + chip */
.row.live {
  background-color: rgba(62, 207, 110, 0.1);
  border-left-color: var(--accent-live);
  border-left-width: 3px;
}

.row.live:hover {
  background-color: rgba(62, 207, 110, 0.16);
}

/* la sessione APERTA nella pagina vince su tutto (anche su live): con molte
   sessioni live il verde è ovunque e senza questo non si capisce quale si
   sta guardando */
.row.active,
.row.live.active {
  background-color: rgba(79, 157, 255, 0.18);
  border-left-color: var(--accent);
  border-left-width: 3px;
  box-shadow: inset 0 0 0 1px rgba(79, 157, 255, 0.35);
}

.live-chip {
  flex: none;
  background-color: var(--accent-live);
  color: #06210f;
  border-radius: 3px;
  padding: 0 0.3rem;
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--muted);
}

.dot.live {
  background-color: var(--accent-live);
  animation: pulse 1.4s infinite;
}

.chip {
  flex: none;
  padding: 0.05rem 0.35rem;
  border-radius: 3px;
  font-size: 0.7rem;
  color: #fff;
}

.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* cerchietto azzurro accanto al nome: numero di round trip */
.rt {
  flex: none;
  background-color: var(--accent);
  color: #fff;
  border-radius: 8px;
  padding: 0 0.35rem;
  font-size: 0.65rem;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
}

/* può comprimersi (con ellissi) prima di far sbordare la riga */
.model {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  font-size: 0.7rem;
}

.tokens {
  flex: none;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  font-size: 0.7rem;
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
  color: var(--muted);
  text-decoration: none;
  padding: 0 0.15rem;
}

.external:hover {
  color: var(--accent);
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
</style>
