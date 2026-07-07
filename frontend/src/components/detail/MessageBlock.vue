<script setup lang="ts">
// Un messaggio della conversazione (role + content). content è stringa o
// array di content block (text/tool_use/tool_result/...). Messaggi lunghi
// vengono troncati con un bottone "mostra tutto". Con `collapsible` il
// messaggio parte chiuso (solo header con anteprima) e si apre dal header.
import { computed, ref } from 'vue'
import ContentBlock from './ContentBlock.vue'

const props = withDefaults(
  defineProps<{
    message: Record<string, any>
    limit?: number
    collapsible?: boolean
  }>(),
  { limit: 1500, collapsible: false }
)

const open = ref(!props.collapsible)

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

/** Anteprima a una riga per il messaggio chiuso: primo testo o tipi di blocco. */
const preview = computed(() => {
  const c = props.message.content
  if (typeof c === 'string') return c.slice(0, 90)
  if (Array.isArray(c)) {
    const firstText = c.find((b) => b?.type === 'text' && b.text)
    if (firstText) return String(firstText.text).slice(0, 90)
    const kinds = c.map((b) => (b?.type === 'tool_use' ? `tool_use ${b.name ?? ''}` : b?.type ?? '?'))
    return kinds.join(', ').slice(0, 90)
  }
  return ''
})

function toggle() {
  if (props.collapsible) open.value = !open.value
}
</script>

<template>
  <div class="message" :class="[`role-${message.role}`, { closed: !open }]">
    <div class="msg-header" :class="{ clickable: collapsible }" @click="toggle">
      <span v-if="collapsible" class="chevron">{{ open ? '▾' : '▸' }}</span>
      <span class="role">{{ message.role }}</span>
      <span v-if="!open" class="preview">{{ preview }}</span>
      <span class="chars">{{ totalChars.toLocaleString('it-IT') }} caratteri</span>
    </div>
    <template v-if="open">
      <template v-if="isStringContent">
        <pre class="pre-wrap">{{ displayString }}</pre>
      </template>
      <template v-else>
        <ContentBlock v-for="(b, i) in blocks" :key="i" :block="b" :max-chars="blockMaxChars" />
      </template>
      <button v-if="truncated" class="show-all" @click="expanded = true">mostra tutto</button>
    </template>
  </div>
</template>

<style scoped>
.message {
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.5rem 0.6rem;
  margin-bottom: 0.5rem;
}

.message.closed {
  padding-top: 0.35rem;
  padding-bottom: 0.35rem;
}

.role-user {
  border-left: 3px solid var(--accent);
}

.role-assistant {
  border-left: 3px solid var(--accent-live);
}

/* messaggio con role "system" DENTRO messages[]: iniezione a livello di
   conversazione, distinta dal campo `system` della richiesta */
.role-system {
  border-left: 3px solid #a78bfa;
}

.msg-header {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 0.35rem;
}

.message.closed .msg-header {
  margin-bottom: 0;
}

.msg-header.clickable {
  cursor: pointer;
  user-select: none;
}

.chevron {
  color: var(--muted);
}

.role {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.preview {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-style: italic;
  opacity: 0.8;
}

.chars {
  margin-left: auto;
  white-space: nowrap;
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
