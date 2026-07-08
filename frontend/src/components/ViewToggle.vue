<script setup lang="ts">
// Segmented Timeline/Dashboard switch, shown at the top of the center pane
// (replaces the single link that used to live in the sessions sidebar).
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSpyStore } from '../stores/spy'

const spy = useSpyStore()
const route = useRoute()
const router = useRouter()

const onDashboard = computed(() => route.path === '/')

/** Timeline destination: the session currently open, or failing that the one featured on the charts. */
const backSessionId = computed(() => spy.currentSessionId ?? spy.featuredSessionId)

function goTimeline() {
  if (backSessionId.value) router.push(`/session/${backSessionId.value}`)
}

function goDashboard() {
  router.push('/')
}
</script>

<template>
  <div class="view-toggle">
    <button
      type="button"
      class="opt"
      :class="{ active: !onDashboard }"
      :disabled="onDashboard && !backSessionId"
      title="Timeline: follow round trips as they happen"
      @click="goTimeline"
    >
      🕐 Timeline
    </button>
    <button
      type="button"
      class="opt"
      :class="{ active: onDashboard }"
      title="Dashboard: charts and totals"
      @click="goDashboard"
    >
      📊 Dashboard
    </button>
  </div>
</template>

<style scoped>
.view-toggle {
  flex: none;
  display: inline-flex;
  gap: 2px;
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 3px;
  width: fit-content;
}

.opt {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--muted);
  padding: 0.35rem 0.7rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.opt:disabled {
  opacity: 0.4;
  cursor: default;
}

.opt.active {
  background-color: var(--panel-alt);
  color: var(--text);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
</style>
