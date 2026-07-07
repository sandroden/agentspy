/**
 * Glifo (emoji) per un tool use, condiviso fra le card della timeline.
 * Scopo didattico: riconoscere a colpo d'occhio la natura di un tool
 * (lettura, scrittura, shell, ricerca, subagente, rete, ...).
 *
 * La mappa è volutamente piccola: i tool sconosciuti ricadono su 🔧, gli
 * MCP (prefisso `mcp__`) su 🔌.
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
}

export function toolIcon(name: string): string {
  if (name.startsWith('mcp__')) return '🔌'
  return EXACT[name] ?? '🔧'
}
