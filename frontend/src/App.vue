<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import SessionsSidebar from './components/SessionsSidebar.vue'
import DetailPanel from './components/DetailPanel.vue'
import { useSpyStore } from './stores/spy'

const spy = useSpyStore()
const { selectedEventId, wsConnected } = storeToRefs(spy)

onMounted(() => {
  void spy.init()
})
</script>

<template>
  <div class="app-layout" :class="{ 'has-detail': selectedEventId != null }">
    <aside class="sidebar">
      <div class="ws-indicator" :title="wsConnected ? 'connesso' : 'disconnesso'">
        <span class="dot" :class="{ connected: wsConnected }"></span>
        <span class="label">{{ wsConnected ? 'live' : 'offline' }}</span>
      </div>
      <SessionsSidebar />
    </aside>
    <main class="center">
      <router-view />
    </main>
    <aside v-if="selectedEventId != null" class="panel">
      <DetailPanel />
    </aside>
  </div>
</template>

<style>
:root {
  --bg: #111318;
  --panel: #181b22;
  --panel-alt: #1f232c;
  --border: #2a2e38;
  --text: #e4e6eb;
  --muted: #8b93a3;
  --accent: #4f9dff;
  --accent-live: #3ecf6e;
  --danger: #e5534b;
  --font: system-ui, -apple-system, 'Segoe UI', sans-serif;
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
  grid-template-columns: 260px 1fr 420px;
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
  background-color: var(--panel);
  border-left: 1px solid var(--border);
  overflow-y: auto;
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
