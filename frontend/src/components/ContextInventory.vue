<script setup lang="ts">
// Cumulative "what the context carries along" list: everything the context
// drags through the session, in order of first appearance. Opened as a modal by
// clicking a "first seen" chip in the timeline (spy.openContextInventory).
// No content: just the list. Clicking a row opens the round trip it appeared in.
import { computed } from 'vue'
import { useSpyStore } from '../stores/spy'
import type { ContextArtifact } from '../types'
import ContextArtifactList from './detail/ContextArtifactList.vue'

const spy = useSpyStore()

const open = computed(() => spy.contextInventoryOpen)
const cwd = computed<string | null | undefined>(() => spy.currentSession?.cwd)

function artifactKey(a: ContextArtifact): string {
  return `${a.kind}|${a.path ?? a.label}`
}

/** First appearance (round trip position + event_id) of every artifact. */
const firstSeen = computed<Map<string, { rtIndex: number; eventId: number }>>(() => {
  const map = new Map<string, { rtIndex: number; eventId: number }>()
  spy.stats.forEach((s, idx) => {
    for (const a of s.artifacts ?? []) {
      const key = artifactKey(a)
      if (!map.has(key)) map.set(key, { rtIndex: idx, eventId: s.event_id })
    }
  })
  return map
})

const items = computed<ContextArtifact[]>(() => spy.cumulativeArtifacts)

function badgeFor(a: ContextArtifact): { text: string; tone: 'new' | 'cached' } | null {
  const f = firstSeen.value.get(artifactKey(a))
  if (!f) return null
  if (f.rtIndex === 0) return { text: 'from RT1', tone: 'cached' }
  return { text: `new · RT${f.rtIndex + 1}`, tone: 'new' }
}

function onPick(a: ContextArtifact) {
  const f = firstSeen.value.get(artifactKey(a))
  if (f) {
    spy.select(f.eventId)
    spy.closeContextInventory()
  }
}

function close() {
  spy.closeContextInventory()
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="ctx-modal-backdrop" @click.self="close">
      <div class="ctx-modal" role="dialog" aria-modal="true" aria-label="Context inventory">
        <header class="ctx-modal-head">
          <div>
            <h2>What the context carries along</h2>
            <p class="sub">{{ items.length }} items · in order of first appearance</p>
          </div>
          <button type="button" class="ctx-close" aria-label="Close" @click="close">✕</button>
        </header>
        <p class="legend">
          <span class="badge cached">from RT1</span> there from the start (then <em>cache_read</em>) ·
          <span class="badge new">new</span> added in a later round trip. Click a row → opens the
          round trip it appeared in.
        </p>
        <div class="ctx-modal-body">
          <p v-if="items.length === 0" class="placeholder">no data for this session.</p>
          <ContextArtifactList
            v-else
            :artifacts="items"
            :cwd="cwd"
            :badge-for="badgeFor"
            @pick="onPick"
          />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ctx-modal-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 45%, transparent);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 6vh 1rem 2rem;
  z-index: 1000;
}
.ctx-modal {
  width: min(720px, 100%);
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  background: var(--panel, #fff);
  color: var(--text, #16211d);
  border: 1px solid var(--border, #dbe4e0);
  border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}
.ctx-modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem 0.75rem;
  border-bottom: 1px solid var(--border, #dbe4e0);
}
.ctx-modal-head h2 {
  margin: 0;
  font-size: 1.1rem;
}
.sub {
  margin: 0.15rem 0 0;
  font-size: 0.82rem;
  color: var(--muted, #5c6b64);
}
.ctx-close {
  flex: 0 0 auto;
  border: none;
  background: transparent;
  font-size: 1.1rem;
  cursor: pointer;
  color: var(--muted, #5c6b64);
  line-height: 1;
  padding: 4px 6px;
  border-radius: 6px;
}
.ctx-close:hover {
  background: var(--panel-alt, #eee);
}
.legend {
  margin: 0;
  padding: 0.6rem 1.25rem;
  font-size: 0.78rem;
  color: var(--muted, #5c6b64);
  line-height: 1.5;
}
.legend .badge {
  font-size: 0.9em;
  font-weight: 700;
  padding: 0 5px;
  border-radius: 999px;
}
.legend .badge.new {
  background: #ffe6c7;
  color: #9a4a00;
}
.legend .badge.cached {
  background: #d9f0e0;
  color: #1c6b3c;
}
.ctx-modal-body {
  overflow-y: auto;
  padding: 0.5rem 1.25rem 1.25rem;
}
.placeholder {
  color: var(--muted, #888);
  font-style: italic;
}
</style>
