<script setup lang="ts">
// Recursive, interactive JSON tree for the DetailPanel's "JSON" tab (and for
// tool_use/input_schema blocks elsewhere). Every object/array node is
// collapsible; the first level (depth 0, the root node passed by the
// caller) is open by default, deeper levels start closed.
// Long strings are truncated with expansion on click.
import { computed, inject, ref } from 'vue'
import { cwdKey } from './detailKeys'
import { relativizeText } from '../../utils/toolIcon'

defineOptions({ name: 'JsonTree' })

const props = withDefaults(
  defineProps<{
    value: unknown
    label?: string | number
    depth?: number
  }>(),
  { depth: 0 }
)

const cwd = inject(cwdKey, ref(null))

const STRING_LIMIT = 240

const expanded = ref(props.depth === 0)
const stringExpanded = ref(false)

const isArray = computed(() => Array.isArray(props.value))
const isObject = computed(() => props.value !== null && typeof props.value === 'object')

const entries = computed<[string | number, unknown][]>(() => {
  if (!isObject.value) return []
  return isArray.value
    ? (props.value as unknown[]).map((v, i): [number, unknown] => [i, v])
    : Object.entries(props.value as Record<string, unknown>)
})

/** props.value relativized to the session cwd, when it's a string. */
const stringValue = computed(() =>
  typeof props.value === 'string' ? relativizeText(props.value, cwd.value) : ''
)

const isLongString = computed(
  () => typeof props.value === 'string' && stringValue.value.length > STRING_LIMIT
)

const displayString = computed(() => {
  const s = stringValue.value
  if (!isLongString.value || stringExpanded.value) return s
  return `${s.slice(0, STRING_LIMIT)}…`
})

function toggleString() {
  if (isLongString.value) stringExpanded.value = !stringExpanded.value
}
</script>

<template>
  <span class="json-node">
    <template v-if="isObject">
      <span class="toggle" @click="expanded = !expanded">{{ expanded ? '▾' : '▸' }}</span>
      <span v-if="label !== undefined" class="key">{{ label }}</span>
      <span v-if="label !== undefined" class="colon">:</span>
      <template v-if="!expanded">
        <span class="preview" @click="expanded = true">
          {{ isArray ? '[' : '{' }} {{ entries.length }} {{ isArray ? 'items' : 'keys' }}
          {{ isArray ? ']' : '}' }}
        </span>
      </template>
      <template v-else>
        <span class="brace">{{ isArray ? '[' : '{' }}</span>
        <span v-if="entries.length === 0" class="empty">empty</span>
        <div v-else class="children">
          <div v-for="[k, v] in entries" :key="String(k)" class="child-row">
            <JsonTree :value="v" :label="k" :depth="depth + 1" />
          </div>
        </div>
        <span class="brace">{{ isArray ? ']' : '}' }}</span>
      </template>
    </template>
    <template v-else>
      <span v-if="label !== undefined" class="key">{{ label }}</span>
      <span v-if="label !== undefined" class="colon">:</span>
      <span v-if="typeof value === 'string'" class="val string" :class="{ clickable: isLongString }" @click="toggleString">
        "{{ displayString }}"
      </span>
      <span v-else-if="typeof value === 'number'" class="val number">{{ value }}</span>
      <span v-else-if="typeof value === 'boolean'" class="val boolean">{{ value }}</span>
      <span v-else-if="value === null" class="val null">null</span>
      <span v-else class="val undefined">undefined</span>
    </template>
  </span>
</template>

<style scoped>
.json-node {
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  font-size: 0.78rem;
  line-height: 1.6;
}

.toggle {
  display: inline-block;
  width: 0.9rem;
  cursor: pointer;
  color: var(--muted);
  user-select: none;
}

.key {
  color: #7dbef0;
}

.colon {
  color: var(--muted);
  margin-right: 0.3rem;
}

.brace {
  color: var(--muted);
}

.preview {
  color: var(--muted);
  font-style: italic;
  cursor: pointer;
}

.preview:hover {
  color: var(--text);
}

.empty {
  color: var(--muted);
  font-style: italic;
  padding-left: 0.3rem;
}

.children {
  padding-left: 1rem;
  border-left: 1px dashed var(--border);
  margin-left: 0.25rem;
}

.val.string {
  color: #d9a86c;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.val.number {
  color: #8fd0a9;
}

.val.boolean {
  color: #d98cd9;
}

.val.null,
.val.undefined {
  color: var(--muted);
  font-style: italic;
}

.clickable {
  cursor: pointer;
}

.clickable:hover {
  text-decoration: underline dotted;
}
</style>
