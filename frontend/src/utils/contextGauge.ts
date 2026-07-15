/**
 * Replica of the statusline's criterion (~/.claude/scripts/thx-statusline.sh):
 * the bar has 12 blocks but the fill is NOT linear with respect to the
 * percentage of context used. Percentages are split into zones
 * (green/amber/yellow/red) with thresholds that depend on the model's
 * context size, and each zone occupies a fixed number of blocks
 * (4/8/11 out of 12): interpolation is linear within a zone, not across
 * zones. Rationale: small context -> can use more of it (higher thresholds);
 * large context -> better to switch sessions sooner (lower thresholds).
 */

/** "context_max:t1:t2:t3" from the statusline, ordered from smallest. */
const PROFILES: { max: number; thresholds: [number, number, number] }[] = [
  { max: 300_000, thresholds: [30, 50, 75] },
  { max: 2_000_000, thresholds: [12, 25, 60] },
]

export const BLOCKS_TOTAL = 12
/** Cumulative blocks filled at the end of each zone (ZONE_BLOCKS). */
const ZONE_BLOCKS = [4, 8, 11]

/** green, amber (light), yellow (dark), red — like ANSI colors 32/93/33/31. */
export const ZONE_COLORS = ['#3fb950', '#f0e14a', '#c9a227', '#f85149'] as const
export const ZONE_NAMES = ['green', 'amber', 'yellow', 'red'] as const

/**
 * Context window per model. The real statusline reads the exact window
 * (`context_window.context_window_size`) straight from Claude Code's payload;
 * agentspy only sees the API traffic, so it derives the window from the model
 * id — a best-effort approximation.
 *
 * Default is 1M: the current families run a 1M window natively (Opus 4.5→4.8,
 * Sonnet 4.5→5, Fable/Mythos 5) and any future model id should inherit that
 * rather than silently regress to 200k (which would put the gauge in a false
 * red at ~5x). Only the known small-window families are pinned to 200k: Haiku
 * (all generations), Claude 1/2/3, and the pre-4.5 Opus/Sonnet 4.x. The "[1m]"
 * marker Claude Code appends to some ids always forces 1M.
 */
export function contextSizeFor(model: string | null | undefined): number {
  if (!model) return 1_000_000
  if (model.includes('[1m]')) return 1_000_000

  // Known small-window families → 200k.
  if (model.includes('haiku')) return 200_000
  if (/claude-[123]([.-]|$)/.test(model)) return 200_000 // Claude 1 / 2 / 3
  if (/glm-4/i.test(model)) return 200_000 // GLM 4.x (~200k); GLM 5.x is 1M (default)

  // Opus/Sonnet 4.x: 4.5 and later are 1M; earlier 4.x kept the classic 200k.
  if (/opus-4-(5|6|7|8)\b/.test(model)) return 1_000_000
  if (/sonnet-4-(5|6)\b/.test(model)) return 1_000_000
  if (/(opus|sonnet)-4(-|\b)/.test(model)) return 200_000

  // Current 1M families (Opus 4.8, Sonnet 5, Fable/Mythos 5) and any unknown /
  // future id default to 1M.
  return 1_000_000
}

function selectThresholds(contextSize: number): [number, number, number] {
  for (const p of PROFILES) {
    if (contextSize <= p.max) return p.thresholds
  }
  return PROFILES[PROFILES.length - 1].thresholds
}

export interface Gauge {
  /** blocks filled out of BLOCKS_TOTAL (per-zone interpolation, like the statusline) */
  filled: number
  /** color of the current zone */
  color: string
  /** zone index: 0 green, 1 amber, 2 yellow, 3 red */
  zone: number
  /** integer percentage used for the calculation */
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
