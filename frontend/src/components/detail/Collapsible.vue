<script setup lang="ts">
// Generic collapsible section: clickable header (title + optional meta,
// e.g. character count) + body with the default slot. Used for the System
// blocks, the tools in "Request", and tool_result in content blocks.
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    meta?: string | null
    defaultOpen?: boolean
  }>(),
  { defaultOpen: false, meta: null }
)

const open = ref(props.defaultOpen)
</script>

<template>
  <div class="collapsible" :class="{ open }">
    <div class="collapsible-header" @click="open = !open">
      <span class="arrow">{{ open ? '▾' : '▸' }}</span>
      <span class="title">{{ title }}</span>
      <span v-if="meta" class="meta">{{ meta }}</span>
    </div>
    <div v-if="open" class="collapsible-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.collapsible {
  border: 1px solid var(--border);
  border-radius: 4px;
  margin-bottom: 0.4rem;
  background-color: var(--panel-alt);
}

.collapsible-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.55rem;
  cursor: pointer;
  font-size: 0.8rem;
  user-select: none;
}

.collapsible-header:hover {
  color: var(--accent);
}

.arrow {
  color: var(--muted);
  width: 0.8rem;
}

.title {
  font-weight: 600;
  flex: 1;
}

.meta {
  color: var(--muted);
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
}

.collapsible-body {
  padding: 0.5rem 0.6rem 0.6rem 1.4rem;
  border-top: 1px solid var(--border);
}
</style>
