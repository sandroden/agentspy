<script setup lang="ts">
// Renders a single Anthropic content block (text / thinking / tool_use /
// tool_result / image / other). Used both for messages in "Request"/"Delta"
// (via MessageBlock) and for the response content in "Response". maxChars,
// if present, truncates text blocks (the "show all" toggle lives in the
// caller, e.g. MessageBlock).
import { computed, inject, ref } from 'vue'
import JsonTree from './JsonTree.vue'
import Collapsible from './Collapsible.vue'
import SystemReminderText from './SystemReminderText.vue'
import { cwdKey } from './detailKeys'
import { relativizeText } from '../../utils/toolIcon'

const props = defineProps<{
  block: Record<string, any>
  maxChars?: number
}>()

const cwd = inject(cwdKey, ref(null))

function truncate(text: string): { text: string; truncated: boolean } {
  if (!props.maxChars || text.length <= props.maxChars) return { text, truncated: false }
  return { text: `${text.slice(0, props.maxChars)}…`, truncated: true }
}

const thinkingOut = computed(() => truncate(relativizeText(String(props.block.thinking ?? ''), cwd.value)))

const toolInputJson = computed(() => {
  let json: string
  try {
    json = JSON.stringify(props.block.input ?? {}, null, 2)
  } catch {
    json = String(props.block.input)
  }
  return relativizeText(json, cwd.value)
})

/** tool_result.content can be a string or an array of blocks (text/image). */
const resultContent = computed(() => props.block.content)
const resultIsString = computed(() => typeof resultContent.value === 'string')
const resultText = computed(() =>
  resultIsString.value ? relativizeText(resultContent.value as string, cwd.value) : ''
)
const resultChars = computed(() => {
  const c = resultContent.value
  if (typeof c === 'string') return c.length
  try {
    return JSON.stringify(c).length
  } catch {
    return 0
  }
})
</script>

<template>
  <div class="content-block" :class="`type-${block.type}`">
    <template v-if="block.type === 'thinking'">
      <div class="label">thinking</div>
      <pre class="pre-wrap thinking-text">{{ thinkingOut.text }}</pre>
    </template>

    <template v-else-if="block.type === 'text'">
      <SystemReminderText :text="String(block.text ?? '')" :max-chars="maxChars" />
    </template>

    <template v-else-if="block.type === 'tool_use'">
      <div class="label">tool_use — {{ block.name }}</div>
      <pre class="pre-wrap code">{{ toolInputJson }}</pre>
    </template>

    <template v-else-if="block.type === 'tool_result'">
      <Collapsible
        :title="`tool_result${block.is_error ? ' (error)' : ''}`"
        :meta="`${resultChars} characters`"
      >
        <pre v-if="resultIsString" class="pre-wrap" :class="{ error: block.is_error }">{{ resultText }}</pre>
        <JsonTree v-else :value="resultContent" />
      </Collapsible>
    </template>

    <template v-else-if="block.type === 'image'">
      <div class="label">image ({{ block.source?.media_type ?? '?' }})</div>
    </template>

    <template v-else>
      <JsonTree :value="block" />
    </template>
  </div>
</template>

<style scoped>
.content-block {
  margin-bottom: 0.5rem;
}

.label {
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 0.15rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.pre-wrap {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: inherit;
  font-size: 0.85rem;
}

.pre-wrap.code {
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  font-size: 0.78rem;
}

.pre-wrap.error {
  color: var(--danger);
}

.type-thinking {
  background-color: var(--panel-alt);
  border-left: 3px solid var(--accent);
  padding: 0.4rem 0.6rem;
  border-radius: 0 4px 4px 0;
}

.thinking-text {
  color: var(--muted);
  font-style: italic;
}

.type-tool_use {
  background-color: var(--panel-alt);
  border-radius: 4px;
  padding: 0.4rem 0.6rem;
}
</style>
