<script setup lang="ts">
import SessionsSidebar from './components/SessionsSidebar.vue'
import DetailPanel from './components/DetailPanel.vue'
</script>

<template>
  <div class="app-layout">
    <div class="sidebar">
      <SessionsSidebar />
    </div>
    <div class="center">
      <router-view />
    </div>
    <div class="panel">
      <DetailPanel />
    </div>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  width: 100%;
  height: 100%;
}

body {
  background-color: #1a1a1a;
  color: #e0e0e0;
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
</style>

<style scoped>
.app-layout {
  display: grid;
  grid-template-columns: 250px 1fr 300px;
  height: 100vh;
  gap: 0;
}

.sidebar {
  background-color: #0f0f0f;
  border-right: 1px solid #333;
  overflow-y: auto;
}

.center {
  background-color: #1a1a1a;
  overflow-y: auto;
}

.panel {
  background-color: #0f0f0f;
  border-left: 1px solid #333;
  overflow-y: auto;
}
</style>
