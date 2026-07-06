<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useSpyStore } from '../stores/spy'
import { formatDuration, formatTokens } from '../utils/format'

const spy = useSpyStore()
const router = useRouter()

const topLevelSessions = computed(() =>
  Object.values(spy.sessions)
    .filter((s) => !s.parent_session_id)
    .slice()
    .sort((a, b) => (b.started_at ?? 0) - (a.started_at ?? 0))
)

function open(id: string) {
  router.push(`/session/${id}`)
}

function totalTokens(s: (typeof topLevelSessions.value)[number]): number {
  const u = s.usage_incl_children
  return u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
}
</script>

<template>
  <div class="home-view">
    <h1>agentspy</h1>
    <p class="subtitle">
      Spia e visualizza in tempo reale la comunicazione fra Claude Code e l'API Anthropic.
    </p>

    <section class="quickstart">
      <h2>Avvio rapido</h2>
      <ol>
        <li><code>cd server && uv run agentspy</code></li>
        <li><code>ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude</code></li>
        <li>
          Per taggare una raccolta (separare run diverse):
          <code>ANTHROPIC_CUSTOM_HEADERS="x-agentspy-tag: mio-tag" claude</code>
        </li>
      </ol>
    </section>

    <section class="sessions">
      <h2>Sessioni</h2>
      <p v-if="topLevelSessions.length === 0" class="empty">
        Nessuna sessione ancora. Avvia il server e una sessione Claude Code per vederla qui.
      </p>
      <div v-else class="cards">
        <div v-for="s in topLevelSessions" :key="s.id" class="card" @click="open(s.id)">
          <div class="card-header">
            <span class="dot" :class="{ live: s.live }"></span>
            <strong>{{ s.title || s.id }}</strong>
          </div>
          <div class="card-meta">
            <span v-if="s.tag" class="chip">{{ s.tag }}</span>
            <span>{{ s.model }}</span>
            <span>{{ formatDuration(s.duration_s) }}</span>
            <span>{{ formatTokens(totalTokens(s)) }} tok</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-view {
  padding: 2rem;
  max-width: 900px;
  margin: 0 auto;
}

h1 {
  font-size: 1.8rem;
  margin-bottom: 0.25rem;
}

.subtitle {
  color: var(--muted);
  margin-bottom: 1.5rem;
}

.quickstart {
  margin-bottom: 2rem;
}

.quickstart ol {
  padding-left: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

code {
  background-color: var(--panel-alt);
  padding: 0.15rem 0.4rem;
  border-radius: 3px;
  font-size: 0.85rem;
}

.empty {
  color: var(--muted);
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.75rem;
}

.card {
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.75rem;
  cursor: pointer;
}

.card:hover {
  border-color: var(--accent);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.4rem;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--muted);
}

.dot.live {
  background-color: var(--accent-live);
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: var(--muted);
}

.chip {
  background-color: var(--panel-alt);
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  color: var(--text);
}
</style>
