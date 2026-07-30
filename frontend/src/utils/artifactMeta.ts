/** Icons and labels for the context artifact kinds (ContextArtifact). */
import type { ArtifactKind } from '../types'

const ICON: Record<ArtifactKind, string> = {
  system: '⚙️',
  'claude-md': '📋',
  memory: '🧠',
  image: '🖼️',
  'at-file': '📎',
  'file-ref': '🔖',
  'read-file': '📄',
  tools: '🔧',
}

/** Short label for the kind (for groupings/legends). */
const KIND_LABEL: Record<ArtifactKind, string> = {
  system: 'System prompt',
  'claude-md': 'Instructions',
  memory: 'Memory',
  image: 'Image',
  'at-file': 'Attached file',
  'file-ref': 'Referenced file (not loaded)',
  'read-file': 'Read file',
  tools: 'Tools',
}

export function artifactIcon(kind: ArtifactKind): string {
  return ICON[kind] ?? '•'
}

export function artifactKindLabel(kind: ArtifactKind): string {
  return KIND_LABEL[kind] ?? kind
}
