/** Utility for the color of a collection tag. */

/**
 * Stable color derived from the tag name (simple hash → hue). Shared between
 * the sidebar and the dashboard, so the "featured" session's chip has the
 * same color as its sidebar row: that visual continuity is what ties
 * "this row → these charts".
 */
export function tagColor(tag: string): string {
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) >>> 0
  const hue = hash % 360
  return `hsl(${hue}, 55%, 45%)`
}
