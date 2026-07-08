/** Utility to recognize the model family and assign it a color. */

export type ModelFamily = 'opus' | 'sonnet' | 'haiku' | 'fable' | 'unknown'

/** Extracts the family ("opus", "sonnet"...) from an Anthropic model string. */
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
 * Identifying color per model, used in subagent bars and legends.
 * `unknown` falls back to the global accent.
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
 * Compact "family-major.minor" label (e.g. "opus-4.8"). Duplicated across
 * the timeline/sidebar/context-fill components: this is the shared version
 * for the newer dashboard components.
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
