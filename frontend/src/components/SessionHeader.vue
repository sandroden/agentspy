<script setup lang="ts">
/**
 * Intestazione di sezione condivisa da Timeline e Dashboard (stesso corpo e
 * stesso carattere del brand "AgentSpy" nella sidebar): nome della sessione,
 * stato live e una riga di metadati (modello · durata · token · round trip).
 */
import { computed } from 'vue'
import type { Session } from '../types'
import { abbreviateModel } from '../utils/model'
import { formatDuration, formatTokens } from '../utils/format'
import ViewToggle from './ViewToggle.vue'

const props = defineProps<{
  session: Session
}>()

/** Nome principale: il tag scelto dall'utente, altrimenti il titolo, altrimenti l'id. */
const name = computed(() => {
  const s = props.session
  if (s.tag) return s.tag
  if (s.title) return s.title
  return s.id.length > 12 ? `${s.id.slice(0, 12)}…` : s.id
})

/** Nome secondario accanto al principale (il titolo, quando il tag è già il nome). */
const subName = computed(() => (props.session.tag ? props.session.title : null))

const isSub = computed(() => !!props.session.parent_session_id)

/** Token totali consumati dalla sessione (input + output + cache). */
const totalTokens = computed(() => {
  const u = props.session.usage
  return u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
})
</script>

<template>
  <header class="session-header">
    <div class="title-row">
      <div class="title-left">
        <h1 class="name">{{ name }}</h1>
        <span v-if="subName" class="sub-name">{{ subName }}</span>
        <span
          class="dot"
          :class="{ live: session.live }"
          :title="session.live ? 'live' : 'ended'"
        ></span>
        <span v-if="isSub" class="badge-sub">sub-agent</span>
      </div>
      <ViewToggle />
    </div>
    <div class="meta-row">
      <span>{{ abbreviateModel(session.model) }}</span>
      <span class="sep">·</span>
      <span>{{ formatDuration(session.duration_s) }}</span>
      <span class="sep">·</span>
      <span class="strong">{{ formatTokens(totalTokens) }} tok</span>
      <span class="sep">·</span>
      <span class="strong">
        {{ session.round_trips }} round trip{{ session.round_trips === 1 ? '' : 's' }}
      </span>
    </div>
    <!-- righe extra della pagina (es. link parent/subagenti nella timeline) -->
    <slot />
  </header>
</template>

<style scoped>
.session-header {
  padding: 0.7rem 1.5rem 0.8rem;
  border-bottom: 1px solid var(--border);
}

.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  /* stessa altezza della riga brand nella sidebar */
  min-height: 34px;
}

.title-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

/* stesso corpo/peso del brand "AgentSpy" nella sidebar */
.name {
  font-size: 1.15rem;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}

.sub-name {
  color: var(--muted);
  font-size: 0.85rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.dot {
  flex: none;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background-color: var(--muted-faint);
}

.dot.live {
  background-color: var(--accent-live);
  animation: pulse 1.4s infinite;
}

.badge-sub {
  flex: none;
  padding: 0.05rem 0.4rem;
  border-radius: 99px;
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  color: var(--muted);
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.4rem;
  font-size: 0.85rem;
  color: var(--muted);
  margin-top: 0.3rem;
  font-variant-numeric: tabular-nums;
}

.sep {
  color: var(--muted-faint);
}

.strong {
  color: var(--text);
  font-weight: 700;
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
