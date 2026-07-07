/** Utility per riconoscere la famiglia di modello e assegnarle un colore. */

export type ModelFamily = 'opus' | 'sonnet' | 'haiku' | 'fable' | 'unknown'

/** Estrae la famiglia ("opus", "sonnet"…) da una stringa modello Anthropic. */
export function modelFamily(model: string | null | undefined): ModelFamily {
  if (!model) return 'unknown'
  const m = model.match(/claude-([a-z]+)/i)
  const family = m?.[1]?.toLowerCase()
  if (family === 'opus' || family === 'sonnet' || family === 'haiku' || family === 'fable') {
    return family
  }
  return 'unknown'
}

/**
 * Colore identificativo per modello, usato nelle barre subagente e nelle
 * legende. `unknown` cade sull'accent globale.
 */
export function modelColor(model: string | null | undefined): string {
  switch (modelFamily(model)) {
    case 'opus':
      return '#a78bfa'
    case 'sonnet':
      return '#22d3ee'
    case 'haiku':
      return '#fbbf24'
    case 'fable':
      return '#f87171'
    default:
      return 'var(--accent)'
  }
}

/**
 * Etichetta compatta "famiglia-major.minor" (es. "opus-4.8"). Duplicata nei
 * tre componenti timeline/sidebar/context-fill: qui è la versione condivisa per
 * i componenti nuovi della dashboard.
 */
export function abbreviateModel(model: string | null | undefined): string {
  if (!model) return '—'
  const m = model.match(/claude-([a-z]+)-(\d+)(?:-(\d+))?/i)
  if (m) {
    const [, family, major, minor] = m
    return minor ? `${family}-${major}.${minor}` : `${family}-${major}`
  }
  return model.length > 14 ? `${model.slice(0, 14)}…` : model
}
