<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useSpyStore, type SessionNode } from '../stores/spy'
import { formatTokens } from '../utils/format'
import type { Session } from '../types'

const spy = useSpyStore()
const router = useRouter()

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

function open(id: string) {
  router.push(`/session/${id}`)
}

function externalHref(id: string): string {
  return `/ui/session/${id}`
}
</script>

<template>
  <nav class="sessions-sidebar">
    <p v-if="rows.length === 0" class="empty">Nessuna sessione</p>
    <div
      v-for="row in rows"
      :key="row.session.id"
      class="row"
      :class="{ active: row.session.id === spy.currentSessionId }"
      :style="{ paddingLeft: `${0.6 + row.depth * 1}rem` }"
      @click="open(row.session.id)"
    >
      <span class="dot" :class="{ live: row.session.live }"></span>
      <span v-if="row.session.tag" class="chip" :style="{ backgroundColor: tagColor(row.session.tag) }">
        {{ row.session.tag }}
      </span>
      <span class="title">{{ row.session.title || row.session.id }}</span>
      <span class="model">{{ abbreviateModel(row.session.model) }}</span>
      <span class="tokens">{{ formatTokens(totalTokens(row.session)) }}</span>
      <span v-if="spy.unseenCounts[row.session.id]" class="badge">
        {{ spy.unseenCounts[row.session.id] }}
      </span>
      <a
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
  </nav>
</template>

<style scoped>
.sessions-sidebar {
  flex: 1;
  overflow-y: auto;
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

.model {
  flex: none;
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
