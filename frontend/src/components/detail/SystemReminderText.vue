<script setup lang="ts">
// Renderizza un blocco di testo di un messaggio distinguendo le sezioni
// <system-reminder>…</system-reminder> (iniettate da Claude Code) dal testo
// utente reale. Due modalità, controllate dal flag `compactView` iniettato
// dal DetailPanel:
//  - espansa: i reminder diventano riquadri evidenziati; il testo normale
//    resta troncato a maxChars (comportamento storico).
//  - compatta: ogni reminder è un chip cliccabile che apre un modal col
//    contenuto completo; il testo utente resta visibile per intero.
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { compactViewKey } from './detailKeys'

const props = defineProps<{
  text: string
  maxChars?: number
}>()

const compactView = inject(compactViewKey, ref(false))

interface Segment {
  kind: 'text' | 'reminder'
  content: string
}

const OPEN = '<system-reminder>'
const CLOSE = '</system-reminder>'

/**
 * Divide il testo in segmenti alternati testo/reminder. Gestisce reminder
 * non chiusi (fino a fine testo) e testo senza reminder (un solo segmento).
 */
function parseSegments(text: string): Segment[] {
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
  return segments.filter((s) => s.kind === 'reminder' || s.content.length > 0)
}

const segments = computed(() => parseSegments(props.text))

/** Nessun reminder presente: percorso identico al vecchio <pre>. */
const hasReminders = computed(() => segments.value.some((s) => s.kind === 'reminder'))

function truncate(text: string): string {
  if (!props.maxChars || text.length <= props.maxChars) return text
  return `${text.slice(0, props.maxChars)}…`
}

/** In vista espansa il testo normale segue il troncamento storico. */
function textFor(content: string): string {
  return compactView.value ? content : truncate(content)
}

function charLabel(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k char`
  return `${n} char`
}

// -- modal (vista compatta) --------------------------------------------------

const modalContent = ref<string | null>(null)

function openModal(content: string) {
  modalContent.value = content
}

function closeModal() {
  modalContent.value = null
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closeModal()
}

// Ascolta Esc a livello di finestra solo mentre il modal è aperto.
watch(modalContent, (v) => {
  if (v !== null) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <template v-for="(seg, i) in segments" :key="i">
    <!-- testo utente reale -->
    <pre v-if="seg.kind === 'text'" class="pre-wrap">{{ textFor(seg.content) }}</pre>

    <!-- reminder, vista compatta: chip -->
    <button
      v-else-if="compactView"
      type="button"
      class="reminder-chip"
      :title="'apri system-reminder'"
      @click="openModal(seg.content)"
    >
      <span class="gear">⚙</span>
      <span>system-reminder</span>
      <span class="chip-meta">{{ charLabel(seg.content.length) }}</span>
    </button>

    <!-- reminder, vista espansa: riquadro evidenziato -->
    <div v-else class="reminder-box">
      <div class="reminder-label">
        <span class="gear">⚙</span>
        <span>system-reminder</span>
        <span class="reminder-meta">{{ charLabel(seg.content.length) }}</span>
      </div>
      <pre class="pre-wrap reminder-text">{{ textFor(seg.content) }}</pre>
    </div>
  </template>

  <!-- placeholder: testo interamente vuoto senza reminder -->
  <pre v-if="segments.length === 0 && !hasReminders" class="pre-wrap"></pre>

  <Teleport to="body">
    <div
      v-if="modalContent !== null"
      class="reminder-overlay"
      @click.self="closeModal"
    >
      <div class="reminder-modal">
        <header class="modal-header">
          <span class="gear">⚙</span>
          <span class="modal-title">system-reminder</span>
          <span class="modal-meta">{{ charLabel(modalContent.length) }}</span>
          <button type="button" class="modal-close" title="chiudi" @click="closeModal">✕</button>
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

/* -- vista espansa: riquadro reminder -- */
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

/* -- vista compatta: chip -- */
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
