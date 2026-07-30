/**
 * Markdown → HTML for the artifact reader (CLAUDE.md, MEMORY.md, .md files,
 * system prompt).
 *
 * `html: false`: the raw HTML in the source is escaped, not interpreted. Two
 * reasons: no injection from content coming from the captured payload, and —
 * educationally the point — the markers Claude Code injects
 * (`<system-reminder>`, `<command-name>`, …) stay visible instead of
 * disappearing as unknown tags.
 */
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: false,
})

export function renderMarkdown(text: string): string {
  return md.render(text)
}

/**
 * Removes the `<n>\t` gutter that the Read tool prepends to every line of a
 * file it loads into the context (also for `@file`, which is eager-loaded via
 * Read). Only for the *rendered* view: the raw view keeps the numbers, which
 * are really in the context and weigh on it.
 *
 * Conservative: it strips only if the majority of the non-empty lines have the
 * gutter, so a file that genuinely starts with a number is left alone.
 */
const GUTTER_RE = /^\s{0,6}\d+\t/

export function stripLineGutter(text: string): string {
  const lines = text.split('\n')
  const nonEmpty = lines.filter((l) => l.trim() !== '')
  if (nonEmpty.length === 0) return text
  const numbered = nonEmpty.filter((l) => GUTTER_RE.test(l)).length
  if (numbered / nonEmpty.length < 0.8) return text
  return lines.map((l) => l.replace(GUTTER_RE, '')).join('\n')
}
