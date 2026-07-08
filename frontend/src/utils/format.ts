/** Formatting of numbers/durations/times for the UI. */

export function formatTokens(n: number | null | undefined): string {
  const value = n ?? 0
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(value)
}

export function formatDuration(s: number | null | undefined): string {
  if (s == null) return '—'
  if (s < 1) return `${Math.round(s * 1000)}ms`
  if (s < 60) return `${s.toFixed(2)}s`
  const minutes = Math.floor(s / 60)
  const seconds = Math.round(s % 60)
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

/** Local HH:MM:SS time from an epoch timestamp in seconds. */
export function formatTime(ts: number | null | undefined): string {
  if (ts == null) return '--:--:--'
  const d = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
