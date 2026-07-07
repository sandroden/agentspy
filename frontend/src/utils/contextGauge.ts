/**
 * Replica del criterio della statusline (~/.claude/scripts/thx-statusline.sh):
 * la barra ha 12 blocchi ma il riempimento NON è lineare rispetto alla
 * percentuale di contesto usato. Le percentuali sono divise in zone
 * (verde/ambra/giallo/rosso) con soglie che dipendono dalla dimensione del
 * contesto del modello, e ogni zona occupa un numero fisso di blocchi
 * (4/8/11 su 12): dentro la zona l'interpolazione è lineare, fra le zone no.
 * Logica: contesto piccolo -> si può usare di più (soglie alte); contesto
 * grande -> conviene cambiare sessione prima (soglie basse).
 */

/** "context_max:t1:t2:t3" della statusline, ordinati dal più piccolo. */
const PROFILES: { max: number; thresholds: [number, number, number] }[] = [
  { max: 300_000, thresholds: [30, 50, 75] },
  { max: 2_000_000, thresholds: [12, 25, 60] },
]

export const BLOCKS_TOTAL = 12
/** Blocchi cumulativi occupati al termine di ogni zona (ZONE_BLOCKS). */
const ZONE_BLOCKS = [4, 8, 11]

/** verde, ambra (chiaro), giallo (scuro), rosso — come i colori ANSI 32/93/33/31. */
export const ZONE_COLORS = ['#3fb950', '#f0e14a', '#c9a227', '#f85149'] as const
export const ZONE_NAMES = ['green', 'amber', 'yellow', 'red'] as const

/**
 * Finestra di contesto per modello: sonnet-5 ha 1M (con o senza il marker
 * "[1m]" nell'id); per gli altri si assume la finestra classica da 200k.
 */
export function contextSizeFor(model: string | null | undefined): number {
  if (!model) return 200_000
  if (model.includes('[1m]') || model.includes('sonnet-5')) return 1_000_000
  return 200_000
}

function selectThresholds(contextSize: number): [number, number, number] {
  for (const p of PROFILES) {
    if (contextSize <= p.max) return p.thresholds
  }
  return PROFILES[PROFILES.length - 1].thresholds
}

export interface Gauge {
  /** blocchi pieni su BLOCKS_TOTAL (interpolazione per zona, come la statusline) */
  filled: number
  /** colore della zona corrente */
  color: string
  /** indice zona: 0 verde, 1 ambra, 2 giallo, 3 rosso */
  zone: number
  /** percentuale intera usata per il calcolo */
  pct: number
}

export function contextGauge(usedTokens: number, contextSize: number): Gauge {
  const pct = Math.round((usedTokens / contextSize) * 100)
  const thresholds = selectThresholds(contextSize)

  let zoneStartPct = 0
  let zoneStartBlocks = 0
  for (let i = 0; i < thresholds.length; i++) {
    if (pct <= thresholds[i]) {
      const span = thresholds[i] - zoneStartPct
      const filled =
        span === 0
          ? ZONE_BLOCKS[i]
          : Math.floor(zoneStartBlocks + ((pct - zoneStartPct) / span) * (ZONE_BLOCKS[i] - zoneStartBlocks))
      return { filled, color: ZONE_COLORS[i], zone: i, pct }
    }
    zoneStartPct = thresholds[i]
    zoneStartBlocks = ZONE_BLOCKS[i]
  }
  return { filled: BLOCKS_TOTAL, color: ZONE_COLORS[3], zone: 3, pct }
}
