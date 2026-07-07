<script setup lang="ts">
// Un messaggio della conversazione (role + content). content è stringa o
// array di content block (text/tool_use/tool_result/...). Messaggi lunghi
// vengono troncati con un bottone "mostra tutto".
import { computed, ref } from 'vue'
import ContentBlock from './ContentBlock.vue'

const props = withDefaults(
  defineProps<{
    message: Record<string, any>
    limit?: number
  }>(),
  { limit: 1500 }
)

const expanded = ref(false)

const isStringContent = computed(() => typeof props.message.content === 'string')

const totalChars = computed(() => {
  const c = props.message.content
  if (typeof c === 'string') return c.length
  try {
    return JSON.stringify(c).length
  } catch {
    return 0
  }
})

const truncated = computed(() => !expanded.value && totalChars.value > props.limit)

const displayString = computed(() => {
  const c = props.message.content as string
  if (!truncated.value) return c
  return `${c.slice(0, props.limit)}…`
})

/** limite per-blocco quando il messaggio è troncato e non espanso. */
const blockMaxChars = computed(() => (truncated.value ? props.limit : undefined))

const blocks = computed(() =>
  Array.isArray(props.message.content) ? (props.message.content as Record<string, any>[]) : []
)
</script>

<template>
  <div class="message" :class="`role-${message.role}`">
    <div class="msg-header">
      <span class="role">{{ message.role }}</span>
      <span class="chars">{{ totalChars.toLocaleString('it-IT') }} caratteri</span>
    </div>
    <template v-if="isStringContent">
      <pre class="pre-wrap">{{ displayString }}</pre>
    </template>
    <template v-else>
      <ContentBlock v-for="(b, i) in blocks" :key="i" :block="b" :max-chars="blockMaxChars" />
    </template>
    <button v-if="truncated" class="show-all" @click="expanded = true">mostra tutto</button>
  </div>
</template>

<style scoped>
.message {
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.5rem 0.6rem;
  margin-bottom: 0.5rem;
}

.role-user {
  border-left: 3px solid var(--accent);
}

.role-assistant {
  border-left: 3px solid var(--accent-live);
}

.msg-header {
  display: flex;
  justify-content: space-between;
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 0.35rem;
}

.role {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.pre-wrap {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: inherit;
  font-size: 0.85rem;
}

.show-all {
  margin-top: 0.4rem;
  background-color: var(--panel);
  color: var(--accent);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0.2rem 0.5rem;
  font-size: 0.75rem;
  cursor: pointer;
}

.show-all:hover {
  border-color: var(--accent);
}
</style>
