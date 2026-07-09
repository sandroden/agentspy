/** Icone ed etichette per i tipi di artefatto del contesto (ContextArtifact). */
import type { ArtifactKind } from '../types'

const ICON: Record<ArtifactKind, string> = {
  system: '⚙️',
  'claude-md': '📋',
  memory: '🧠',
  image: '🖼️',
  'at-file': '📎',
  'read-file': '📄',
  tools: '🔧',
}

/** Etichetta breve del tipo (per raggruppamenti/legende). */
const KIND_LABEL: Record<ArtifactKind, string> = {
  system: 'System prompt',
  'claude-md': 'Istruzioni',
  memory: 'Memoria',
  image: 'Immagine',
  'at-file': 'File allegato',
  'read-file': 'File letto',
  tools: 'Tools',
}

export function artifactIcon(kind: ArtifactKind): string {
  return ICON[kind] ?? '•'
}

export function artifactKindLabel(kind: ArtifactKind): string {
  return KIND_LABEL[kind] ?? kind
}
