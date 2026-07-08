<script setup lang="ts">
// Renders a message's text block, distinguishing three things Claude Code
// injects into the "user" slot from the actual user text:
//  - <system-reminder>…</system-reminder> sections;
//  - a slash-command / skill invocation (the <command-*> wrapper plus the
//    SKILL.md body it injects — real, measurable context cost).
// Two modes, controlled by the `compactView` flag injected by DetailPanel:
//  - expanded: injections become highlighted boxes; normal text stays
//    truncated at maxChars (legacy behavior).
//  - compact: each injection is a clickable chip (with its char count) that
//    opens a modal with the full content; the user text stays fully visible.
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { compactViewKey, cwdKey } from './detailKeys'
import { relativizeText } from '../../utils/toolIcon'
import { splitCommandInjection } from '../../utils/command'

const props = defineProps<{
  text: string
  maxChars?: number
}>()

const compactView = inject(compactViewKey, ref(false))
const cwd = inject(cwdKey, ref(null))

const relativizedText = computed(() => relativizeText(props.text, cwd.value))

interface Segment {
  kind: 'text' | 'reminder' | 'command'
  content: string
  label?: string // command: nome della skill/comando (es. /okf:okf)
}

const OPEN = '<system-reminder>'
const CLOSE = '</system-reminder>'

/**
 * Splits text into alternating text/reminder segments. Handles unclosed
 * reminders (to end of text) and text with no reminders (a single segment).
 */
function parseReminderSegments(text: string): Segment[] {
  const segments: Segment[] = []
  let i = 0
  while (i < text.length) {
    const start = text.indexOf(OPEN, i)
    if (start === -1) {
      segments.push({ kind: 'text', content: text.slice(i) })
      break
    }
    if (start > i) segments.push({ kind: 'text', content: text.slice(i, start) })
    const contentStart = start + OPEN.length
    const end = text.indexOf(CLOSE, contentStart)
    if (end === -1) {
      segments.push({ kind: 'reminder', content: text.slice(contentStart) })
      break
    }
    segments.push({ kind: 'reminder', content: text.slice(contentStart, end) })
    i = end + CLOSE.length
  }
  return segments
}

/**
 * A slash-command wrapper (if present) runs to the end of the block: split it
 * off as its own segment and parse only the preceding text for reminders.
 */
function parseSegments(text: string): Segment[] {
  const injection = splitCommandInjection(text)
  const segments = injection
    ? [
        ...parseReminderSegments(injection.before),
        { kind: 'command' as const, content: injection.injected, label: injection.command.name },
      ]
    : parseReminderSegments(text)
  return segments.filter((s) => s.kind !== 'text' || s.content.length > 0)
}

const segments = computed(() => parseSegments(relativizedText.value))

/** No injection present: same path as the old <pre>. */
const hasReminders = computed(() => segments.value.some((s) => s.kind !== 'text'))

function truncate(text: string): string {
  if (!props.maxChars || text.length <= props.maxChars) return text
  return `${text.slice(0, props.maxChars)}…`
}

/** In expanded view, normal text follows the legacy truncation. */
function textFor(content: string): string {
  return compactView.value ? content : truncate(content)
}

function charLabel(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k char`
  return `${n} char`
}

// -- modal (vista compatta) --------------------------------------------------

const modalContent = ref<string | null>(null)
const modalTitle = ref('system-reminder')

function openModal(content: string, title = 'system-reminder') {
  modalContent.value = content
  modalTitle.value = title
}

function closeModal() {
  modalContent.value = null
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closeModal()
}

// Listen for Esc at the window level only while the modal is open.
watch(modalContent, (v) => {
  if (v !== null) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <template v-for="(seg, i) in segments" :key="i">
    <!-- actual user text -->
    <pre v-if="seg.kind === 'text'" class="pre-wrap">{{ textFor(seg.content) }}</pre>

    <!-- command/skill, compact view: chip -->
    <button
      v-else-if="seg.kind === 'command' && compactView"
      type="button"
      class="reminder-chip command-chip"
      :title="'open skill / command payload'"
      @click="openModal(seg.content, seg.label || 'command')"
    >
      <span class="gear">🎓</span>
      <span>{{ seg.label || 'command' }}</span>
      <span class="chip-meta">{{ charLabel(seg.content.length) }} iniettati</span>
    </button>

    <!-- command/skill, expanded view: highlighted box -->
    <div v-else-if="seg.kind === 'command'" class="reminder-box command-box">
      <div class="reminder-label command-label">
        <span class="gear">🎓</span>
        <span>skill / command · {{ seg.label }}</span>
        <span class="reminder-meta">{{ charLabel(seg.content.length) }} iniettati</span>
      </div>
      <pre class="pre-wrap reminder-text">{{ textFor(seg.content) }}</pre>
    </div>

    <!-- reminder, compact view: chip -->
    <button
      v-else-if="compactView"
      type="button"
      class="reminder-chip"
      :title="'open system-reminder'"
      @click="openModal(seg.content)"
    >
      <span class="gear">⚙</span>
      <span>system-reminder</span>
      <span class="chip-meta">{{ charLabel(seg.content.length) }}</span>
    </button>

    <!-- reminder, expanded view: highlighted box -->
    <div v-else class="reminder-box">
      <div class="reminder-label">
        <span class="gear">⚙</span>
        <span>system-reminder</span>
        <span class="reminder-meta">{{ charLabel(seg.content.length) }}</span>
      </div>
      <pre class="pre-wrap reminder-text">{{ textFor(seg.content) }}</pre>
    </div>
  </template>

  <!-- placeholder: entirely empty text with no reminders -->
  <pre v-if="segments.length === 0 && !hasReminders" class="pre-wrap"></pre>

  <Teleport to="body">
    <div
      v-if="modalContent !== null"
      class="reminder-overlay"
      @click.self="closeModal"
    >
      <div class="reminder-modal">
        <header class="modal-header">
          <span class="gear">{{ modalTitle === 'system-reminder' ? '⚙' : '🎓' }}</span>
          <span class="modal-title">{{ modalTitle }}</span>
          <span class="modal-meta">{{ charLabel(modalContent.length) }}</span>
          <button type="button" class="modal-close" title="close" @click="closeModal">✕</button>
        </header>
        <div class="modal-body">
          <pre class="pre-wrap">{{ modalContent }}</pre>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pre-wrap {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: inherit;
  font-size: 0.85rem;
}

.gear {
  font-size: 0.8em;
}

/* -- expanded view: reminder box -- */
.reminder-box {
  background-color: rgba(217, 140, 217, 0.08);
  border-left: 3px solid #d98cd9;
  border-radius: 0 4px 4px 0;
  padding: 0.35rem 0.55rem;
  margin: 0.35rem 0;
}

.reminder-label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #d98cd9;
  margin-bottom: 0.25rem;
}

.reminder-meta,
.chip-meta,
.modal-meta {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.reminder-text {
  color: var(--muted);
}

/* -- compact view: chip -- */
.reminder-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background-color: var(--panel-alt);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: #d98cd9;
  padding: 0.15rem 0.45rem;
  margin: 0.2rem 0;
  font-size: 0.75rem;
  font-family: inherit;
  cursor: pointer;
}

.reminder-chip:hover {
  border-color: #d98cd9;
}

/* -- command/skill: teal, distinto dal reminder viola -- */
.command-box {
  background-color: rgba(58, 176, 162, 0.08);
  border-left-color: #3ab0a2;
}

.command-label {
  color: #3ab0a2;
}

.command-chip {
  color: #3ab0a2;
}

.command-chip:hover {
  border-color: #3ab0a2;
}

/* -- modal -- */
.reminder-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  z-index: 1000;
}

.reminder-modal {
  background-color: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  width: 100%;
  max-width: 720px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.6rem 0.8rem;
  border-bottom: 1px solid var(--border);
  color: #d98cd9;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.modal-title {
  font-weight: 700;
}

.modal-close {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--muted);
  font-size: 1rem;
  cursor: pointer;
  line-height: 1;
  padding: 0.1rem 0.3rem;
  text-transform: none;
}

.modal-close:hover {
  color: var(--danger);
}

.modal-body {
  overflow-y: auto;
  padding: 0.8rem;
}
</style>
