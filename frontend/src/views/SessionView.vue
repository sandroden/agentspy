<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSpyStore } from '../stores/spy'
import TimeControls from '../components/TimeControls.vue'
import TimelineView from '../components/TimelineView.vue'
import ContextFillPanel from '../components/ContextFillPanel.vue'
import { formatDuration, formatTokens } from '../utils/format'

const props = defineProps<{
  id: string
}>()

const spy = useSpyStore()
const router = useRouter()

const showContextFill = ref(false)

function load(id: string) {
  void spy.openSession(id)
}

onMounted(() => load(props.id))
watch(
  () => props.id,
  (id) => load(id)
)

const session = computed(() => spy.currentSession)

const children = computed(() =>
  Object.values(spy.sessions).filter((s) => s.parent_session_id === props.id)
)

const parent = computed(() => {
  const pid = session.value?.parent_session_id
  return pid ? (spy.sessions[pid] ?? null) : null
})

function goTo(id: string) {
  router.push(`/session/${id}`)
}
</script>

<template>
  <div class="session-view">
    <header v-if="session" class="session-header">
      <div class="title-row">
        <h1>{{ session.title || session.id }}</h1>
        <span class="dot" :class="{ live: session.live }"></span>
      </div>
      <div class="meta-row">
        <span v-if="session.tag" class="chip">{{ session.tag }}</span>
        <span>{{ session.model }}</span>
        <span>{{ formatDuration(session.duration_s) }}</span>
        <span>{{ session.turns }} turni · {{ session.round_trips }} round trip</span>
      </div>
      <div class="usage-row">
        <div class="usage-block">
          <span class="usage-label">sessione</span>
          <span>in {{ formatTokens(session.usage.input_tokens) }}</span>
          <span>out {{ formatTokens(session.usage.output_tokens) }}</span>
          <span>cache-r {{ formatTokens(session.usage.cache_read_tokens) }}</span>
          <span>cache-w {{ formatTokens(session.usage.cache_write_tokens) }}</span>
        </div>
        <div class="usage-block incl">
          <span class="usage-label">incl. subagenti</span>
          <span>in {{ formatTokens(session.usage_incl_children.input_tokens) }}</span>
          <span>out {{ formatTokens(session.usage_incl_children.output_tokens) }}</span>
          <span>cache-r {{ formatTokens(session.usage_incl_children.cache_read_tokens) }}</span>
          <span>cache-w {{ formatTokens(session.usage_incl_children.cache_write_tokens) }}</span>
        </div>
      </div>
      <div v-if="parent || children.length" class="links-row">
        <span v-if="parent" class="chip link" @click="goTo(parent.id)">
          ↑ {{ parent.title || parent.id }}
        </span>
        <span v-for="c in children" :key="c.id" class="chip link" @click="goTo(c.id)">
          ↳ {{ c.title || c.id }}
        </span>
      </div>
    </header>
    <p v-else class="loading">Caricamento sessione…</p>

    <TimeControls />

    <div class="toggle-row">
      <label>
        <input v-model="showContextFill" type="checkbox" />
        mostra riempimento contesto
      </label>
    </div>

    <ContextFillPanel v-if="showContextFill" />
    <TimelineView />
  </div>
</template>

<style scoped>
.session-view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.session-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
}

.title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.title-row h1 {
  font-size: 1.3rem;
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background-color: var(--muted);
}

.dot.live {
  background-color: var(--accent-live);
  animation: pulse 1.4s infinite;
}

.meta-row,
.links-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  font-size: 0.85rem;
  color: var(--muted);
  margin-top: 0.4rem;
}

.usage-row {
  display: flex;
  gap: 1.5rem;
  margin-top: 0.6rem;
  flex-wrap: wrap;
}

.usage-block {
  display: flex;
  gap: 0.6rem;
  font-size: 0.8rem;
  align-items: baseline;
}

.usage-block.incl {
  color: var(--accent);
}

.usage-label {
  color: var(--muted);
  font-weight: 600;
  margin-right: 0.2rem;
}

.chip {
  background-color: var(--panel-alt);
  padding: 0.1rem 0.5rem;
  border-radius: 3px;
}

.chip.link {
  cursor: pointer;
}

.chip.link:hover {
  border: 1px solid var(--accent);
}

.toggle-row {
  padding: 0.4rem 1.5rem;
  font-size: 0.85rem;
  color: var(--muted);
}

.loading {
  padding: 2rem;
  color: var(--muted);
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
