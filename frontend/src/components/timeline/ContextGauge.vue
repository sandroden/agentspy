<script setup lang="ts">
// "Statusline" mini-bar: context fill at the time of a round trip, using the
// same (non-linear) criterion as the terminal statusline.
// The context used is input + cache_read + cache_write of the request.
import { computed } from 'vue'
import { BLOCKS_TOTAL, contextGauge, contextSizeFor } from '../../utils/contextGauge'
import { formatTokens } from '../../utils/format'
import type { Usage } from '../../types'

const props = defineProps<{ usage: Usage; model?: string | null; contextSize?: number }>()

const usedTokens = computed(
  () => props.usage.input_tokens + props.usage.cache_read_tokens + props.usage.cache_write_tokens
)

const size = computed(() => props.contextSize ?? contextSizeFor(props.model))

const gauge = computed(() => contextGauge(usedTokens.value, size.value))

const cells = computed(() =>
  Array.from({ length: BLOCKS_TOTAL }, (_, i) => i < gauge.value.filled)
)

const title = computed(
  () =>
    `context ${gauge.value.pct}% (${formatTokens(usedTokens.value)}/${formatTokens(size.value)}) — non-linear bar, same criterion as the statusline`
)
</script>

<template>
  <div class="context-gauge" :title="title">
    <span class="bracket">[</span>
    <span class="cells">
      <span
        v-for="(full, i) in cells"
        :key="i"
        class="cell"
        :class="{ full }"
        :style="full ? { backgroundColor: gauge.color } : undefined"
      ></span>
    </span>
    <span class="bracket">]</span>
    <span class="pct" :style="{ color: gauge.color }">{{ gauge.pct }}%</span>
  </div>
</template>

<style scoped>
.context-gauge {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  font-size: 0.68rem;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  white-space: nowrap;
}

.bracket {
  opacity: 0.6;
}

.cells {
  display: inline-flex;
  gap: 1px;
}

.cell {
  width: 5px;
  height: 9px;
  border-radius: 1px;
  background-color: var(--border);
  opacity: 0.55;
}

.cell.full {
  opacity: 1;
}

.pct {
  margin-left: 0.25rem;
  font-weight: 600;
  min-width: 3ch;
  text-align: right;
}
</style>
