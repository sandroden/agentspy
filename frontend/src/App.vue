<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import SessionsSidebar from './components/SessionsSidebar.vue'
import DetailPanel from './components/DetailPanel.vue'
import { useSpyStore } from './stores/spy'
import { useTheme } from './composables/useTheme'

const spy = useSpyStore()
const { selectedEventId, wsConnected } = storeToRefs(spy)
useTheme().init()

// -- larghezza colonna dettaglio (ridimensionabile col mouse) ----------------
const DETAIL_WIDTH_KEY = 'agentspy.detailWidth'
const MIN_WIDTH = 320
const DEFAULT_WIDTH = 420

function clampWidth(w: number): number {
  const max = Math.round(window.innerWidth * 0.7)
  return Math.min(Math.max(w, MIN_WIDTH), Math.max(max, MIN_WIDTH))
}

function loadWidth(): number {
  const raw = Number(localStorage.getItem(DETAIL_WIDTH_KEY))
  return Number.isFinite(raw) && raw > 0 ? clampWidth(raw) : DEFAULT_WIDTH
}

const detailWidth = ref(loadWidth())
const dragging = ref(false)

const layoutStyle = computed(() => ({ '--detail-width': `${detailWidth.value}px` }))

let startX = 0
let startWidth = 0

function onDragMove(e: MouseEvent) {
  // The handle is on the left edge: dragging left widens the panel.
  detailWidth.value = clampWidth(startWidth - (e.clientX - startX))
}

function onDragEnd() {
  dragging.value = false
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  document.body.style.userSelect = ''
  localStorage.setItem(DETAIL_WIDTH_KEY, String(detailWidth.value))
}

function startDrag(e: MouseEvent) {
  e.preventDefault()
  startX = e.clientX
  startWidth = detailWidth.value
  dragging.value = true
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

onMounted(() => {
  void spy.init()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
})
</script>

<template>
  <div
    class="app-layout"
    :class="{ 'has-detail': selectedEventId != null, dragging }"
    :style="layoutStyle"
  >
    <aside class="sidebar">
      <div class="ws-indicator" :title="wsConnected ? 'connected' : 'disconnected'">
        <span class="dot" :class="{ connected: wsConnected }"></span>
        <span class="label">{{ wsConnected ? 'live' : 'offline' }}</span>
      </div>
      <SessionsSidebar />
    </aside>
    <main class="center">
      <router-view />
    </main>
    <aside v-if="selectedEventId != null" class="panel">
      <div
        class="resize-handle"
        :class="{ active: dragging }"
        title="drag to resize"
        @mousedown="startDrag"
      ></div>
      <DetailPanel />
    </aside>
  </div>
</template>

<style>
/* Light theme (default) — "readable" palette from the AgentSpy design direction.
   Dark theme below overrides the same variable names, so most components
   (which only ever reference these vars) restyle automatically. */
:root {
  --bg: #fbfaf7;
  --panel: #f5f2ea;
  --panel-alt: #ffffff;
  --border: #eae4d6;
  --text: #20242c;
  --muted: #6b6455;
  --muted-faint: #8a8370;
  --accent: #7c4fd1;
  --accent-live: #34d399;
  --danger: #e0574a;
  /* series colors shared by the timeline swimlane and the dashboard charts */
  --c-user: #4e8fff;
  --c-assistant: #c084fc;
  --c-tool: #f5a623;
  /* the LLM (Claude) card in the timeline: green, per the Claude Design palette */
  --c-llm: #1f9d76;
  --font: system-ui, -apple-system, 'Segoe UI', sans-serif;
}

:root[data-theme='dark'] {
  --bg: #111318;
  --panel: #181b22;
  --panel-alt: #1f232c;
  --border: #2a2e38;
  --text: #e4e6eb;
  --muted: #8b93a3;
  --muted-faint: #6b7480;
  --accent: #a78bfa;
  --accent-live: #3ecf6e;
  --danger: #e5534b;
  --c-user: #4e8fff;
  --c-assistant: #c084fc;
  --c-tool: #f5a623;
  --c-llm: #3ecf8e;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  width: 100%;
  height: 100%;
}

body {
  background-color: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: 14px;
  line-height: 1.5;
}
</style>

<style scoped>
.app-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  height: 100vh;
}

.app-layout.has-detail {
  grid-template-columns: 260px 1fr var(--detail-width, 420px);
}

.app-layout.dragging {
  cursor: col-resize;
}

.sidebar {
  background-color: var(--panel);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.center {
  background-color: var(--bg);
  overflow-y: auto;
}

.panel {
  position: relative;
  background-color: var(--panel);
  border-left: 1px solid var(--border);
  overflow-y: auto;
}

.resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 5;
  background-color: transparent;
  transition: background-color 0.12s;
}

.resize-handle:hover,
.resize-handle.active {
  background-color: var(--accent);
}

.ws-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.8rem;
  color: var(--muted);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--danger);
}

.dot.connected {
  background-color: var(--accent-live);
}
</style>
