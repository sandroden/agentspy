/**
 * Mechanical, v1 plain-language caption for a round trip: derived only from
 * which tools were called (not from actual message content, which would
 * need an LLM summarization pass — out of scope here). Good enough to teach
 * "what kind of thing just happened", not a real narrative summary.
 */
import type { EventSummary } from '../types'

const VERBS: Record<string, string> = {
  Read: 'Reads a file',
  Write: 'Writes a file',
  Edit: 'Edits a file',
  MultiEdit: 'Edits a file',
  NotebookEdit: 'Edits a notebook',
  Bash: 'Runs a shell command',
  BashOutput: 'Checks a running command',
  Grep: 'Searches the codebase',
  Glob: 'Looks for files',
  WebFetch: 'Fetches a web page',
  WebSearch: 'Searches the web',
  TodoWrite: 'Updates its task list',
  Task: 'Delegates to a sub-agent',
  Agent: 'Delegates to a sub-agent',
}

function verbFor(name: string): string {
  if (name.startsWith('mcp__')) return 'Calls an external tool'
  return VERBS[name] ?? 'Calls a tool'
}

export function mechanicalCaption(event: EventSummary): string {
  const names = event.tool_names
  if (names.length === 0) {
    return 'No tool this time — writes the answer directly.'
  }
  const unique = [...new Set(names)]
  if (unique.length === 1) {
    const verb = verbFor(unique[0])
    return names.length > 1 ? `${verb}, ${names.length} times.` : `${verb}.`
  }
  return `Uses ${unique.length} different tools before continuing.`
}

/** Fixed, generic caption for a sub-agent delegation marker — true regardless
 * of session content, so safe to show without per-content generation. */
export const SUBAGENT_CAPTION =
  'The Agent tool delegates a task to a sub-agent with its own context and its own round trips — not a system event, but a call like any other.'
