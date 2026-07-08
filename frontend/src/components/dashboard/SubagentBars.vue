<script setup lang="ts">
/**
 * Horizontal bars for subagents (child sessions): length = total tokens used
 * (usage of that session alone), color by model. Click opens the session.
 * The panel hides itself if there are no children.
 */
import { computed } from 'vue'
import type { Session } from '../../types'
import { abbreviateModel, modelColor } from '../../utils/model'
import { formatTokens } from '../../utils/format'

const props = defineProps<{ subagents: Session[] }>()
const emit = defineEmits<{ (e: 'open', sessionId: string): void }>()

function totalTokens(s: Session): number {
  const u = s.usage
  return u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens
}

const rows = computed(() => {
  const items = props.subagents.map((s) => ({
    id: s.id,
    label: s.title || s.tag || s.agent_id || s.id,
    model: s.model,
    color: modelColor(s.model),
    tokens: totalTokens(s),
  }))
  items.sort((a, b) => b.tokens - a.tokens)
  return items
})

const maxTokens = computed(() => Math.max(1, ...rows.value.map((r) => r.tokens)))

function widthPct(tokens: number): string {
  return `${Math.max(1.5, (tokens / maxTokens.value) * 100)}%`
}
</script>

<template>
  <div v-if="rows.length > 0" class="subagent-bars">
    <div v-for="r in rows" :key="r.id" class="row" @click="emit('open', r.id)">
      <div class="head">
        <span class="name">{{ r.label }}</span>
        <span class="model">{{ abbreviateModel(r.model) }}</span>
        <span class="tokens">{{ formatTokens(r.tokens) }} tok</span>
      </div>
      <div class="track">
        <div class="fill" :style="{ width: widthPct(r.tokens), backgroundColor: r.color }"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.subagent-bars {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.row {
  cursor: pointer;
  padding: 0.2rem 0.25rem;
  border-radius: 4px;
}

.row:hover {
  background-color: var(--panel-alt);
}

.head {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  font-size: 0.78rem;
  margin-bottom: 0.25rem;
}

.name {
  color: var(--text);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model {
  color: var(--muted);
  font-size: 0.72rem;
}

.tokens {
  margin-left: auto;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  flex: none;
}

.track {
  height: 12px;
  background-color: var(--panel-alt);
  border-radius: 3px;
  overflow: hidden;
}

.fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.2s ease;
}
</style>
