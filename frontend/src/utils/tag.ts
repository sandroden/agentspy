/** Utility per il colore di un tag di raccolta. */

/**
 * Colore stabile derivato dal nome del tag (semplice hash → hue). Condiviso
 * fra la sidebar e la dashboard, così la chip della sessione "featured" ha lo
 * stesso colore della sua riga nella sidebar: è quella continuità visiva a
 * legare "questa riga → questi grafici".
 */
export function tagColor(tag: string): string {
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) >>> 0
  const hue = hash % 360
  return `hsl(${hue}, 55%, 45%)`
}
