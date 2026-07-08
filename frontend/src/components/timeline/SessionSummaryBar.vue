<script setup lang="ts">
// Shown in place of the Glossary once its tips are dismissed: a compact
// usage summary for the open session (and, if any, its sub-agents), plus a
// "?" button to bring the tips back.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatTokens } from '../../utils/format'

const emit = defineEmits<{ (e: 'show-tips'): void }>()

const spy = useSpyStore()

const session = computed(() => spy.currentSession)

const hasSubagents = computed(() => {
  const id = session.value?.id
  if (!id) return false
  return Object.values(spy.sessions).some((s) => s.parent_session_id === id)
})
</script>

<template>
  <div v-if="session" class="summary-bar">
    <div class="group">
      <span class="group-label">Session</span>
      <div class="card">
        <span class="label">input (new)</span>
        <span class="value">{{ formatTokens(session.usage.input_tokens) }}</span>
      </div>
      <div class="card">
        <span class="label">output</span>
        <span class="value">{{ formatTokens(session.usage.output_tokens) }}</span>
      </div>
      <div class="card">
        <span class="label">cache read</span>
        <span class="value">{{ formatTokens(session.usage.cache_read_tokens) }}</span>
      </div>
      <div class="card">
        <span class="label">cache write</span>
        <span class="value">{{ formatTokens(session.usage.cache_write_tokens) }}</span>
      </div>
    </div>

    <div v-if="hasSubagents" class="group">
      <span class="group-label">+ Sub-agents</span>
      <div class="card card--sub">
        <span class="label">input (new)</span>
        <span class="value">{{ formatTokens(session.usage_incl_children.input_tokens) }}</span>
      </div>
      <div class="card card--sub">
        <span class="label">output</span>
        <span class="value">{{ formatTokens(session.usage_incl_children.output_tokens) }}</span>
      </div>
      <div class="card card--sub">
        <span class="label">cache read</span>
        <span class="value">{{ formatTokens(session.usage_incl_children.cache_read_tokens) }}</span>
      </div>
      <div class="card card--sub">
        <span class="label">cache write</span>
        <span class="value">{{ formatTokens(session.usage_incl_children.cache_write_tokens) }}</span>
      </div>
    </div>

    <button class="show-btn" title="Show the explanations" @click="emit('show-tips')">?</button>
  </div>
</template>

<style scoped>
.summary-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1.1rem;
  border-bottom: 1px solid var(--border);
  background-color: var(--panel-alt);
  padding: 0.55rem 1.25rem;
}

.group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.group-label {
  font: 700 0.65rem system-ui;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted-faint);
  margin-right: 0.1rem;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 0.25rem 0.55rem;
  min-width: 78px;
}

.card--sub {
  opacity: 0.65;
  padding: 0.2rem 0.45rem;
  min-width: auto;
}

.label {
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--muted-faint);
}

.value {
  font-size: 0.85rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text);
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}

.show-btn {
  margin-left: auto;
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background-color: var(--panel);
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 700;
  cursor: pointer;
}

.show-btn:hover {
  color: var(--text);
  border-color: var(--muted);
}
</style>
