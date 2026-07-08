<script setup lang="ts">
// Dismissible glossary bar: three terms needed to read the swimlane below.
// Visibility is owned by the parent (TimelineView), which shows a session
// summary in its place once dismissed (see SessionSummaryBar.vue).
const visible = defineModel<boolean>({ default: true })

function hide() {
  visible.value = false
}

const TERMS = [
  {
    icon: '💬',
    term: 'Turn',
    def: 'your message (User Prompt) plus all the work Claude does to answer it.',
  },
  {
    icon: '🔁',
    term: 'Round trip',
    def: 'a single request/response with the model: it may ask to use a tool before continuing.',
  },
  {
    icon: '👆',
    term: 'Navigate',
    def: 'scroll through the chain of events and click a round trip to read its details on the right.',
  },
]
</script>

<template>
  <div v-if="visible" class="glossary">
    <div v-for="t in TERMS" :key="t.term" class="card">
      <span class="icon">{{ t.icon }}</span>
      <div class="body">
        <b>{{ t.term }}</b>
        <span>{{ t.def }}</span>
      </div>
    </div>
    <button class="close-btn" title="Hide the explanations" @click="hide">✕</button>
  </div>
</template>

<style scoped>
.glossary {
  border-bottom: 1px solid var(--border);
  background-color: var(--panel-alt);
  padding: 0.6rem 1.25rem;
  display: flex;
  gap: 0.9rem;
}

.card {
  flex: 1;
  display: flex;
  gap: 0.55rem;
  align-items: flex-start;
  background-color: var(--panel);
  border-radius: 9px;
  padding: 0.55rem 0.7rem;
}

.icon {
  font-size: 1rem;
  line-height: 1.2;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  font-size: 0.75rem;
  color: var(--muted);
}

.body b {
  color: var(--text);
  font-size: 0.78rem;
}

.close-btn {
  flex: none;
  align-self: flex-start;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background-color: var(--panel);
  color: var(--muted);
  font-size: 0.7rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: var(--text);
  border-color: var(--muted);
}
</style>
