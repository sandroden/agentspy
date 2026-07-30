<script setup lang="ts">
// Presentational list of the items making up a request to the LLM (a teaching
// inventory). No content: just icon + label + size + optional path/note.
// Used by ContextInventory (the cumulative session modal).
//
// Two distinct actions per row: `pick` (click on the row → read the content)
// and `goto` (click on the badge → open the round trip where it appeared).
import type { ContextArtifact } from '../../types'
import { formatTokens } from '../../utils/format'
import { relativizeText } from '../../utils/toolIcon'
import { artifactIcon } from '../../utils/artifactMeta'

const props = defineProps<{
  artifacts: ContextArtifact[]
  cwd?: string | null
  /** Shows a badge (e.g. "new"/"cached") next to each row. */
  badgeFor?: (a: ContextArtifact) => { text: string; tone: 'new' | 'cached' } | null
}>()

const emit = defineEmits<{
  (e: 'pick', a: ContextArtifact): void
  (e: 'goto', a: ContextArtifact): void
}>()

function sizeLabel(a: ContextArtifact): string {
  if (a.count != null && a.kind === 'tools') return `${a.count} tools`
  if (a.chars != null) return `${formatTokens(a.chars)} char`
  return ''
}

function pathLabel(a: ContextArtifact): string {
  if (!a.path) return ''
  return relativizeText(a.path, props.cwd)
}
</script>

<template>
  <ul class="artifacts">
    <li
      v-for="(a, i) in artifacts"
      :key="i"
      class="artifact"
      :class="{ clickable: true }"
      title="open the content"
      @click="emit('pick', a)"
    >
      <span class="icon" aria-hidden="true">{{ artifactIcon(a.kind) }}</span>
      <span class="body">
        <span class="label">{{ a.label }}</span>
        <span v-if="pathLabel(a)" class="path" :title="a.path ?? ''">{{ pathLabel(a) }}</span>
        <span v-if="a.description" class="desc">{{ a.description }}</span>
      </span>
      <span class="right">
        <button
          v-if="badgeFor && badgeFor(a)"
          type="button"
          class="badge"
          :class="badgeFor(a)!.tone"
          title="go to the round trip where it appeared"
          @click.stop="emit('goto', a)"
        >{{ badgeFor(a)!.text }}</button>
        <span class="size">{{ sizeLabel(a) }}</span>
      </span>
    </li>
  </ul>
</template>

<style scoped>
.artifacts {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.artifact {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  border: 1px solid var(--border, #e2e2e2);
  background: var(--surface, #fbfbfb);
}
.artifact.clickable {
  cursor: pointer;
}
.artifact.clickable:hover {
  border-color: var(--accent, #7aa2f7);
}
.icon {
  flex: 0 0 auto;
  font-size: 0.95em;
}
.body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
}
.label {
  font-weight: 600;
}
.path {
  font-family: var(--mono, monospace);
  font-size: 0.82em;
  opacity: 0.75;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.desc {
  font-size: 0.8em;
  opacity: 0.6;
  font-style: italic;
}
.right {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 6px;
}
.size {
  font-variant-numeric: tabular-nums;
  font-size: 0.82em;
  opacity: 0.7;
}
.badge {
  font-size: 0.7em;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid transparent;
  cursor: pointer;
  font-family: inherit;
}
.badge:hover {
  border-color: currentColor;
}
.badge.new {
  background: #ffe6c7;
  color: #9a4a00;
}
.badge.cached {
  background: #d9f0e0;
  color: #1c6b3c;
}
</style>
