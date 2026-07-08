<script setup lang="ts">
// One round trip rendered as the 3-column swimlane row: Trigger | Claude (LLM) |
// Tools. The user bubble only appears on the first round trip of a turn
// (userText prop set); every other row leaves that column empty so the grid
// stays aligned.
import { computed } from 'vue'
import { useSpyStore } from '../../stores/spy'
import { formatDuration, formatTime } from '../../utils/format'
import { relativizeHint, toolIcon, truncateMiddle } from '../../utils/toolIcon'
import { parseSlashCommand } from '../../utils/command'
import { mechanicalCaption } from '../../utils/caption'
import { artifactIcon } from '../../utils/artifactMeta'
import type { EventSummary } from '../../types'
import ContextGauge from './ContextGauge.vue'

const props = defineProps<{
  event: EventSummary
  rtIndex: number
  rtTotal: number
  userText?: string
}>()

const spy = useSpyStore()

/**
 * The trigger column shows what kicked off the turn — all delivered in the
 * same "role: user" slot of the payload, but not all from the human:
 *  - inside a subagent's session the trigger is the task the parent delegated;
 *  - the top-level session can be resumed by an async task-notification;
 *  - otherwise it's really you.
 */
const trigger = computed(() => {
  const isSubagent = props.event.session_id
    ? spy.sessions[props.event.session_id]?.parent_session_id != null
    : false
  if (isSubagent) return { icon: '🤖', label: 'Parent task', kind: 'subagent' }
  const t = props.userText ?? ''
  if (/^\s*<task-notification>/.test(t)) return { icon: '🔔', label: 'Task done', kind: 'notify' }
  // Slash command / skill: il turno è stato aperto da un comando, non da testo
  // libero — lo si etichetta col nome (es. /okf:okf). Il corpo iniettato dalla
  // skill (il costo di contesto) è quantificato nel pannello di dettaglio.
  const cmd = parseSlashCommand(t)
  if (cmd) return { icon: '🎓', label: `Command ${cmd.name}`, kind: 'command' }
  return { icon: '🧑', label: 'You', kind: 'user' }
})

const selected = computed(() => spy.selectedEventId === props.event.id)
const isError = computed(() => props.event.status != null && props.event.status !== 200)
const caption = computed(() => mechanicalCaption(props.event))

/** Best-effort: only if the full payload is already cached (previous click). */
const hasThinking = computed(() => {
  const detail = spy.detailCache[props.event.id]
  const payload = detail?.payload as { response?: { message?: { content?: unknown[] } } } | undefined
  const content = payload?.response?.message?.content
  if (!Array.isArray(content)) return false
  return content.some(
    (block) => block && typeof block === 'object' && 'type' in block && (block as { type: string }).type === 'thinking'
  )
})

const toolBadges = computed<{ name: string; hint: string; full: string }[]>(() => {
  const cwd = props.event.session_id ? spy.sessions[props.event.session_id]?.cwd : null
  const uses = props.event.tool_uses?.length
    ? props.event.tool_uses
    : props.event.tool_names.map((name) => ({ name, hint: '' }))
  return uses.map((u) => {
    const relative = relativizeHint(u.hint, cwd)
    return { name: u.name, hint: truncateMiddle(relative), full: u.hint }
  })
})

function onClick() {
  void spy.select(props.event.id)
}

/**
 * Elementi del contesto visti per la PRIMA volta in questo round trip: la chip
 * compare una sola volta, nel round trip in cui l'elemento entra. Click → apre
 * l'elenco cumulativo ("cosa si porta dietro il contesto"). Sono divisi per
 * provenienza:
 *  - allegati dall'utente (@file, immagini incollate) → dentro la bolla azzurra;
 *  - contesto iniettato dall'harness (system prompt, CLAUDE.md, MEMORY.md, tools)
 *    → fuori dalla bolla verde di Claude, perché è input, non la risposta.
 */
const newArtifacts = computed(() => spy.newArtifactsByEvent[props.event.id] ?? [])
const USER_KINDS = new Set(['at-file', 'image'])
const userArtifacts = computed(() => newArtifacts.value.filter((a) => USER_KINDS.has(a.kind)))
const systemArtifacts = computed(() => newArtifacts.value.filter((a) => !USER_KINDS.has(a.kind)))

function openInventory() {
  spy.openContextInventory()
}
</script>

<template>
  <div class="rt-row" :data-event-id="event.id">
    <div class="col col-user">
      <!-- userText !== undefined marks the turn's first round trip. Show the
           bubble when it carries text, or (even textless) for a subagent/notify
           trigger so its label survives, or when the user attached files this
           round trip — but not an empty "You". -->
      <div
        v-if="userText !== undefined && (userText || trigger.kind !== 'user') || userArtifacts.length"
        class="bubble-user"
        :class="`bubble-user--${trigger.kind}`"
      >
        <div class="bubble-label">{{ trigger.icon }} {{ trigger.label }}</div>
        <p v-if="userText" class="bubble-text bubble-text--clamp" :title="userText">{{ userText }}</p>
        <!-- allegati dell'utente (@file / immagini incollate): dentro l'azzurro -->
        <div v-if="userArtifacts.length" class="ctx-attach">
          <button
            v-for="(a, i) in userArtifacts"
            :key="i"
            type="button"
            class="ctx-chip"
            :class="`ctx-chip--${a.kind}`"
            :title="a.path || a.label"
            @click="openInventory"
          >
            <span class="ctx-chip-icon">{{ artifactIcon(a.kind) }}</span>
            <span class="ctx-chip-label">{{ a.label }}</span>
          </button>
        </div>
      </div>
    </div>

    <div class="col col-claude">
      <div
        class="bubble-claude"
        :class="{ selected, error: isError }"
        @click="onClick"
      >
        <div class="bubble-meta">
          <span class="rt-num">round trip {{ rtIndex }}/{{ rtTotal }}</span>
          <span class="time">{{ formatTime(event.ts_start) }}</span>
          <span class="dur">{{ formatDuration(event.duration_s) }}</span>
          <span v-if="hasThinking" class="thinking">🧠 thinking</span>
          <span v-if="isError" class="status-badge">status {{ event.status }}</span>
          <ContextGauge :usage="event.usage" :model="event.model" class="ctx" />
        </div>
        <p v-if="event.snippet" class="bubble-text">{{ event.snippet }}</p>
      </div>
      <p class="caption">💡 {{ caption }}</p>
      <!-- contesto iniettato dall'harness: FUORI dalla bolla verde (è input,
           non la risposta del modello) -->
      <div v-if="systemArtifacts.length" class="ctx-sys">
        <span class="ctx-sys-label">🆕 nel contesto:</span>
        <button
          v-for="(a, i) in systemArtifacts"
          :key="i"
          type="button"
          class="ctx-chip"
          :class="`ctx-chip--${a.kind}`"
          :title="a.path || a.label"
          @click="openInventory"
        >
          <span class="ctx-chip-icon">{{ artifactIcon(a.kind) }}</span>
          <span class="ctx-chip-label">{{ a.label }}</span>
        </button>
      </div>
    </div>

    <div class="col col-tools">
      <template v-if="toolBadges.length">
        <div v-for="(tool, i) in toolBadges" :key="`${tool.name}-${i}`" class="tool-chip" :title="tool.full || undefined">
          <span class="tool-icon">{{ toolIcon(tool.name) }}</span>
          <span class="tool-name">{{ tool.name }}</span>
          <span v-if="tool.hint" class="tool-hint">{{ tool.hint }}</span>
        </div>
      </template>
      <div v-else class="final-tag">✅ Final answer — no more tools</div>
    </div>
  </div>
</template>

<style scoped>
.rt-row {
  display: grid;
  grid-template-columns: 130px 1fr 320px;
  gap: 10px;
  padding: 12px 0;
  border-bottom: 1px dashed var(--border);
  align-items: start;
}

.col-user {
  min-width: 0;
}

.bubble-user {
  --c-trigger: var(--c-user);
  background-color: color-mix(in srgb, var(--c-trigger) 10%, var(--panel-alt));
  border: 1px solid color-mix(in srgb, var(--c-trigger) 26%, var(--panel-alt));
  border-radius: 10px;
  padding: 10px 12px;
}

/* Async task-notification: same "role: user" slot, but not the human — flag it amber. */
.bubble-user--notify {
  --c-trigger: #d9840a;
}

/* Subagent's own session: the trigger is the task delegated by the parent — purple, like the subagent lane. */
.bubble-user--subagent {
  --c-trigger: var(--c-assistant);
}

/* Slash command / skill invocation: teal, distinto dal prompt libero. */
.bubble-user--command {
  --c-trigger: #3ab0a2;
}

.bubble-label {
  font: 700 11px system-ui;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--c-trigger);
  margin-bottom: 6px;
}

.bubble-text {
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--text);
}

.bubble-text--clamp {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  cursor: help;
}

.col-claude {
  min-width: 0;
}

.bubble-claude {
  background-color: color-mix(in srgb, var(--c-llm) 8%, var(--panel-alt));
  border: 1px solid color-mix(in srgb, var(--c-llm) 26%, var(--border));
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
}

.bubble-claude:hover {
  border-color: var(--c-llm);
}

.bubble-claude.selected {
  outline: 2px solid var(--c-llm);
  outline-offset: 2px;
}

.bubble-claude.error {
  border-color: var(--danger);
}

.bubble-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font: 11px 'JetBrains Mono', ui-monospace, monospace;
  color: var(--muted);
  margin-bottom: 6px;
}

.rt-num {
  color: var(--text);
  font-weight: 700;
}

.time,
.dur {
  font-variant-numeric: tabular-nums;
}

.thinking {
  color: var(--c-assistant);
  background-color: color-mix(in srgb, var(--c-assistant) 14%, transparent);
  padding: 1px 7px;
  border-radius: 99px;
  font-family: 'Inter', sans-serif;
}

.status-badge {
  color: #fff;
  background-color: var(--danger);
  padding: 1px 7px;
  border-radius: 4px;
  font-weight: 700;
}

.ctx {
  margin-left: auto;
}

.caption {
  margin: 6px 0 0 2px;
  font-size: 12px;
  font-style: italic;
  color: var(--muted-faint);
}

.col-tools {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.tool-chip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  background-color: color-mix(in srgb, var(--c-tool) 12%, var(--panel-alt));
  border: 1px solid color-mix(in srgb, var(--c-tool) 35%, var(--border));
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
  color: color-mix(in srgb, var(--c-tool) 55%, var(--text));
}

.tool-name {
  font-weight: 600;
}

.tool-hint {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
}

.final-tag {
  display: inline-block;
  font: 700 11px system-ui;
  color: color-mix(in srgb, var(--accent-live) 55%, var(--text));
  background-color: color-mix(in srgb, var(--accent-live) 16%, var(--panel-alt));
  padding: 4px 10px;
  border-radius: 99px;
  width: fit-content;
}

/* Allegati dell'utente (@file / immagini): dentro la bolla azzurra, sotto il testo. */
.ctx-attach {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

/* Contesto di sistema: banda sotto la bolla verde (fuori: è input, non risposta). */
.ctx-sys {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

.ctx-sys-label {
  font: 700 10.5px system-ui;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}

.ctx-chip {
  --c-chip: var(--c-user);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 600 11.5px system-ui;
  color: color-mix(in srgb, var(--c-chip) 60%, var(--text));
  background-color: color-mix(in srgb, var(--c-chip) 12%, var(--panel-alt));
  border: 1px solid color-mix(in srgb, var(--c-chip) 32%, var(--border));
  border-radius: 99px;
  padding: 3px 10px;
  cursor: pointer;
}

.ctx-chip:hover {
  border-color: var(--c-chip);
  background-color: color-mix(in srgb, var(--c-chip) 20%, var(--panel-alt));
}

.ctx-chip:focus-visible {
  outline: 2px solid var(--c-chip);
  outline-offset: 2px;
}

.ctx-chip-icon {
  font-size: 0.95em;
}

/* Colori per tipo: system/istruzioni sul tono LLM, allegati (immagini/@file) in ambra. */
.ctx-chip--system,
.ctx-chip--tools {
  --c-chip: var(--c-llm);
}
.ctx-chip--claude-md,
.ctx-chip--memory {
  --c-chip: var(--c-assistant);
}
.ctx-chip--image,
.ctx-chip--at-file {
  --c-chip: #d9840a;
}
</style>
