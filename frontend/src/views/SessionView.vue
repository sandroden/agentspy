<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSpyStore } from '../stores/spy'
import TimeControls from '../components/TimeControls.vue'
import TimelineView from '../components/TimelineView.vue'
import ContextFillPanel from '../components/ContextFillPanel.vue'
import ContextInventory from '../components/ContextInventory.vue'
import SessionHeader from '../components/SessionHeader.vue'

const props = defineProps<{
  id: string
}>()

const spy = useSpyStore()
const router = useRouter()
const route = useRoute()

const showContextFill = ref(false)

/**
 * Deep-link a un round trip: /session/<id>?event=<eventId> (usato dai punti
 * dei grafici in dashboard, ma l'URL è anche condivisibile). Mette in pausa
 * il player su quell'evento — il watch sul cursore in TimelineView scrolla
 * alla card — e ne apre il dettaglio nel pannello destro.
 */
async function jumpToQueryEvent() {
  const eventId = Number(route.query.event)
  if (!Number.isFinite(eventId) || eventId <= 0) return
  const idx = spy.events.findIndex((e) => e.id === eventId)
  if (idx === -1) return
  await nextTick() // lascia passare lo scroll-to-bottom del cambio sessione
  spy.setCursor(idx)
  void spy.select(eventId)
}

async function load(id: string) {
  await spy.openSession(id)
  await jumpToQueryEvent()
}

onMounted(() => void load(props.id))
watch(
  () => props.id,
  (id) => void load(id),
)

const session = computed(() => spy.currentSession)

const children = computed(() =>
  Object.values(spy.sessions).filter((s) => s.parent_session_id === props.id),
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
    <SessionHeader v-if="session" :session="session">
      <div v-if="parent || children.length" class="links-row">
        <span v-if="parent" class="chip link" @click="goTo(parent.id)">
          ↑ {{ parent.title || parent.id }}
        </span>
        <span v-for="c in children" :key="c.id" class="chip link" @click="goTo(c.id)">
          ↳ {{ c.title || c.id }}
        </span>
      </div>
    </SessionHeader>
    <p v-else class="loading">Loading session…</p>

    <TimeControls />

    <div class="toggle-row">
      <label>
        <input v-model="showContextFill" type="checkbox" />
        show context fill
      </label>
    </div>

    <ContextFillPanel v-if="showContextFill" />
    <TimelineView />
    <!-- modale "cosa si porta dietro il contesto": aperta dal click su una chip -->
    <ContextInventory />
  </div>
</template>

<style scoped>
.session-view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.links-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  font-size: 0.85rem;
  color: var(--muted);
  margin-top: 0.4rem;
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
</style>
