/**
 * Glyph (emoji) for a tool use, shared across the timeline cards.
 * Didactic purpose: recognize a tool's nature at a glance
 * (read, write, shell, search, subagent, network, ...).
 *
 * The map is deliberately small: unknown tools fall back to 🔧, MCP tools
 * (prefix `mcp__`) to 🔌.
 */

const EXACT: Record<string, string> = {
  Read: '📄',
  Write: '✏️',
  Edit: '✏️',
  MultiEdit: '✏️',
  NotebookEdit: '✏️',
  Bash: '💻',
  BashOutput: '💻',
  Grep: '🔍',
  Glob: '🔍',
  Task: '🤖',
  Agent: '🤖',
  WebFetch: '🌐',
  WebSearch: '🌐',
  TodoWrite: '☑️',
  Skill: '🎓',
}

export function toolIcon(name: string): string {
  if (name.startsWith('mcp__')) return '🔌'
  return EXACT[name] ?? '🔧'
}

/**
 * Same idea as relativizeHint but for arbitrary-length text where the cwd
 * may appear anywhere, not just as the whole string (a tool_result body, a
 * system-reminder, a raw JSON blob, a Bash command with the path in the
 * middle): replaces every occurrence of `cwd/` with '', global rather than
 * anchored.
 */
export function relativizeText(text: string, cwd: string | null | undefined): string {
  if (!text || !cwd) return text
  return text.split(`${cwd}/`).join('')
}

/**
 * Makes a tool's argument hint readable: if it's an absolute path inside the
 * session's working directory, makes it relative (whole-string case, e.g.
 * `hint === cwd`) or strips the cwd wherever it appears (e.g. a Bash command
 * with the path embedded mid-string); visual truncation is left to CSS (the
 * full text goes in the title).
 */
export function relativizeHint(hint: string, cwd: string | null | undefined): string {
  if (!hint) return ''
  if (cwd && hint === cwd) return '.'
  return relativizeText(hint, cwd)
}

/**
 * Truncates in the middle instead of at the end: for a file path the tail
 * (the actual file name) matters more than the directory prefix.
 */
export function truncateMiddle(text: string, maxLen = 34): string {
  if (text.length <= maxLen) return text
  const headLen = Math.ceil((maxLen - 1) / 2)
  const tailLen = Math.floor((maxLen - 1) / 2)
  return `${text.slice(0, headLen)}…${text.slice(text.length - tailLen)}`
}
