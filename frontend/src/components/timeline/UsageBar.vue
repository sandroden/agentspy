<script setup lang="ts">
// Mini barra orizzontale proporzionale ai 4 contatori di usage. Legenda
// completa disponibile via `title` nativo (tooltip al hover).
import { computed } from 'vue'
import { formatTokens } from '../../utils/format'
import type { Usage } from '../../types'

const props = defineProps<{ usage: Usage }>()

const total = computed(
  () =>
    props.usage.cache_read_tokens +
    props.usage.cache_write_tokens +
    props.usage.input_tokens +
    props.usage.output_tokens
)

function pct(n: number): string {
  if (total.value <= 0) return '0%'
  return `${(n / total.value) * 100}%`
}

const legend = computed(() => {
  const u = props.usage
  return [
    `cache-read ${formatTokens(u.cache_read_tokens)}`,
    `cache-write ${formatTokens(u.cache_write_tokens)}`,
    `input ${formatTokens(u.input_tokens)}`,
    `output ${formatTokens(u.output_tokens)}`,
  ].join(' · ')
})
</script>

<template>
  <div class="usage-bar" :title="legend">
    <template v-if="total > 0">
      <span class="seg cache-read" :style="{ width: pct(usage.cache_read_tokens) }"></span>
      <span class="seg cache-write" :style="{ width: pct(usage.cache_write_tokens) }"></span>
      <span class="seg input" :style="{ width: pct(usage.input_tokens) }"></span>
      <span class="seg output" :style="{ width: pct(usage.output_tokens) }"></span>
    </template>
    <span v-else class="seg empty"></span>
  </div>
</template>

<style scoped>
.usage-bar {
  --seg-cache-read: #8b93a3;
  --seg-cache-write: #b47cf0;
  --seg-input: #4f9dff;
  --seg-output: #3ecf6e;
  display: flex;
  height: 6px;
  width: 100%;
  min-width: 60px;
  border-radius: 3px;
  overflow: hidden;
  background-color: var(--panel-alt);
}

.seg {
  height: 100%;
}

.seg.cache-read {
  background-color: var(--seg-cache-read);
}

.seg.cache-write {
  background-color: var(--seg-cache-write);
}

.seg.input {
  background-color: var(--seg-input);
}

.seg.output {
  background-color: var(--seg-output);
}

.seg.empty {
  width: 100%;
  background-color: var(--panel-alt);
}
</style>
