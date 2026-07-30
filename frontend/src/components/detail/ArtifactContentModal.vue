<script setup lang="ts">
// Reader for a single context artifact: shows what actually entered the
// context (CLAUDE.md, MEMORY.md, system prompt, @file, file read by the agent,
// pasted image, tool definitions). The content is not in the inventory — it is
// fetched on demand from GET /api/events/:id/artifact.
//
// Nested over the ContextInventory modal (higher z-index): Esc closes this one
// first, the list stays open underneath.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchArtifactContent } from '../../api/client'
import type { ArtifactContent, ContextArtifact } from '../../types'
import { artifactIcon, artifactKindLabel } from '../../utils/artifactMeta'
import { formatTokens } from '../../utils/format'
import { renderMarkdown, stripLineGutter } from '../../utils/markdown'
import { relativizeText } from '../../utils/toolIcon'

const props = defineProps<{
  artifact: ContextArtifact
  /** round trip the content is read from (first appearance of the artifact). */
  eventId: number
  /** 1-based position of that round trip, for the "as it was at RT N" hint. */
  rtNumber?: number
  cwd?: string | null
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const item = ref<ArtifactContent | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
/** markdown only: rendered (default) or as-sent source. */
const raw = ref(false)

const artifactKey = computed(
  () => `${props.artifact.kind}|${props.artifact.path ?? props.artifact.label}`,
)

const pathLabel = computed(() =>
  props.artifact.path ? relativizeText(props.artifact.path, props.cwd) : '',
)

const isMarkdown = computed(() => item.value?.format === 'markdown')
// Rendered view: without the line-number gutter of the Read tool (the raw view
// keeps it — those characters are in the context).
const html = computed(() =>
  isMarkdown.value && item.value?.content
    ? renderMarkdown(stripLineGutter(item.value.content))
    : '',
)

async function load() {
  loading.value = true
  error.value = null
  try {
    const data = await fetchArtifactContent(props.eventId, artifactKey.value)
    item.value = data
    if (data === null) error.value = 'content not available for this artifact'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    emit('close')
  }
}

onMounted(() => {
  load()
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
watch(artifactKey, load)
</script>

<template>
  <Teleport to="body">
    <div class="art-backdrop" @click.self="emit('close')">
      <div class="art-modal" role="dialog" aria-modal="true" :aria-label="artifact.label">
        <header class="art-head">
          <span class="icon" aria-hidden="true">{{ artifactIcon(artifact.kind) }}</span>
          <div class="titles">
            <h3>{{ artifact.label }}</h3>
            <p class="meta">
              <span class="kind">{{ artifactKindLabel(artifact.kind) }}</span>
              <span v-if="pathLabel" class="path" :title="artifact.path ?? ''">{{ pathLabel }}</span>
              <!-- weight: the inventory's, not recomputed here -->
              <span v-if="artifact.chars != null" class="chars"
                >{{ formatTokens(artifact.chars) }} char</span
              >
              <span v-if="rtNumber" class="rt">as sent in RT{{ rtNumber }}</span>
            </p>
          </div>
          <button
            v-if="isMarkdown"
            type="button"
            class="toggle"
            :title="raw ? 'render the markdown' : 'show the source as sent'"
            @click="raw = !raw"
          >
            {{ raw ? 'rendered' : 'raw' }}
          </button>
          <button type="button" class="art-close" aria-label="Close" @click="emit('close')">
            ✕
          </button>
        </header>

        <div class="art-body">
          <p v-if="loading" class="placeholder">loading…</p>
          <p v-else-if="error" class="placeholder">{{ error }}</p>
          <template v-else-if="item">
            <div v-if="item.images.length" class="images">
              <img v-for="(src, i) in item.images" :key="i" :src="src" :alt="item.label" />
            </div>
            <div v-if="isMarkdown && !raw" class="md" v-html="html"></div>
            <pre v-else-if="item.content" class="pre-wrap">{{ item.content }}</pre>
            <p v-else-if="!item.images.length" class="placeholder">empty content.</p>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.art-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 55%, transparent);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 4vh 1rem 2rem;
  /* above ContextInventory (1000): this is a nested dialog */
  z-index: 1100;
}
.art-modal {
  width: min(920px, 100%);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  background: var(--panel, #fff);
  color: var(--text, #16211d);
  border: 1px solid var(--border, #dbe4e0);
  border-radius: 14px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.35);
  overflow: hidden;
}
.art-head {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.9rem 1.1rem 0.7rem;
  border-bottom: 1px solid var(--border, #dbe4e0);
}
.art-head .icon {
  font-size: 1.1rem;
  line-height: 1.4;
}
.titles {
  flex: 1 1 auto;
  min-width: 0;
}
.art-head h3 {
  margin: 0;
  font-size: 1rem;
}
.meta {
  margin: 0.15rem 0 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.6rem;
  font-size: 0.78rem;
  color: var(--muted, #5c6b64);
}
.meta .path {
  font-family: var(--mono, monospace);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.meta .chars {
  font-variant-numeric: tabular-nums;
}
.meta .rt {
  font-style: italic;
}
.toggle {
  flex: 0 0 auto;
  border: 1px solid var(--border, #dbe4e0);
  background: var(--panel-alt, #f2f4f3);
  color: var(--muted, #5c6b64);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 999px;
  cursor: pointer;
}
.toggle:hover {
  color: var(--text, #16211d);
}
.art-close {
  flex: 0 0 auto;
  border: none;
  background: transparent;
  font-size: 1.05rem;
  cursor: pointer;
  color: var(--muted, #5c6b64);
  line-height: 1;
  padding: 4px 6px;
  border-radius: 6px;
}
.art-close:hover {
  background: var(--panel-alt, #eee);
}
.art-body {
  overflow: auto;
  padding: 0.9rem 1.1rem 1.2rem;
}
.placeholder {
  color: var(--muted, #888);
  font-style: italic;
}
.pre-wrap {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--mono, monospace);
  font-size: 0.82rem;
  line-height: 1.5;
}
.images {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin-bottom: 0.8rem;
}
.images img {
  max-width: 100%;
  border: 1px solid var(--border, #dbe4e0);
  border-radius: 8px;
}

/* rendered markdown */
.md {
  font-size: 0.9rem;
  line-height: 1.6;
}
.md :deep(h1),
.md :deep(h2),
.md :deep(h3),
.md :deep(h4) {
  margin: 1.1em 0 0.4em;
  line-height: 1.25;
}
.md :deep(h1) {
  font-size: 1.35em;
}
.md :deep(h2) {
  font-size: 1.18em;
}
.md :deep(h3) {
  font-size: 1.05em;
}
.md :deep(p),
.md :deep(ul),
.md :deep(ol),
.md :deep(blockquote) {
  margin: 0.5em 0;
}
.md :deep(ul),
.md :deep(ol) {
  padding-left: 1.4em;
}
.md :deep(li) {
  margin: 0.15em 0;
}
.md :deep(code) {
  font-family: var(--mono, monospace);
  font-size: 0.88em;
  background: var(--panel-alt, #f2f4f3);
  border-radius: 4px;
  padding: 0.1em 0.35em;
}
.md :deep(pre) {
  background: var(--panel-alt, #f2f4f3);
  border: 1px solid var(--border, #dbe4e0);
  border-radius: 8px;
  padding: 0.7em 0.9em;
  overflow-x: auto;
}
.md :deep(pre code) {
  background: none;
  padding: 0;
}
.md :deep(blockquote) {
  border-left: 3px solid var(--border, #dbe4e0);
  padding-left: 0.8em;
  color: var(--muted, #5c6b64);
}
.md :deep(table) {
  border-collapse: collapse;
  display: block;
  overflow-x: auto;
}
.md :deep(th),
.md :deep(td) {
  border: 1px solid var(--border, #dbe4e0);
  padding: 0.3em 0.6em;
}
.md :deep(hr) {
  border: none;
  border-top: 1px solid var(--border, #dbe4e0);
  margin: 1em 0;
}
.md :deep(a) {
  color: var(--accent, #2f6f52);
}
</style>
