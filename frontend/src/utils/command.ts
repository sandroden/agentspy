/**
 * Recognizing a skill / slash-command invocation inside a user message.
 *
 * Claude Code expands a typed `/namespace:name args` into a block that gets
 * injected into the user message:
 *
 *   <command-message>name</command-message>
 *   <command-name>/namespace:name</command-name>
 *   <command-args>args</command-args>
 *   Base directory for this skill: /…      ← the injected SKILL.md follows here
 *   # …skill body…
 *
 * That injected body is real context cost: showing it (and measuring it) is
 * the didactic point. A skill invoked by the model, instead, shows up as a
 * `tool_use` named `Skill` — handled by toolIcon(); here we only deal with
 * the slash-command form.
 */

const NAME_RE = /<command-name>\s*([\s\S]*?)\s*<\/command-name>/
const ARGS_RE = /<command-args>\s*([\s\S]*?)\s*<\/command-args>/
const MSG_OPEN = '<command-message>'
const NAME_OPEN = '<command-name>'
// "Raw" form (the one the UserPromptSubmit hook carries): "/name" or
// "/namespace:name" as the first token, followed by a space or the end. The
// lookahead avoids false positives on paths ("/tmp/foo", "/home/sandro").
const RAW_RE = /^\/([A-Za-z][\w-]*(?::[\w-]+)?)(?=\s|$)([^\n]*)/

export interface SlashCommand {
  name: string // e.g. "/okf:okf" (leading slash kept)
  args: string // e.g. "produce .okf" ("" when absent)
}

/** Detects a slash-command both in the expanded form (wrapper) and in the raw
 *  "/name args" one (the text the UserPromptSubmit hook carries). */
export function parseSlashCommand(text: string): SlashCommand | null {
  if (!text) return null
  const m = text.match(NAME_RE)
  if (m && m[1]) {
    const a = text.match(ARGS_RE)
    return { name: m[1].trim(), args: a ? a[1].trim() : '' }
  }
  const raw = text.trimStart().match(RAW_RE)
  if (raw) return { name: `/${raw[1]}`, args: (raw[2] ?? '').trim() }
  return null
}

export interface CommandInjection {
  before: string // user text before the wrapper (can be '')
  command: SlashCommand
  injected: string // wrapper + injected skill body (the context cost)
}

/** For the detail panel: splits a text block carrying the expanded wrapper
 *  into the preceding user text and the injected block. Returns null when
 *  there is no expanded wrapper (the raw "/name" form injects nothing). */
export function splitCommandInjection(text: string): CommandInjection | null {
  if (!text) return null
  let start = text.indexOf(MSG_OPEN)
  if (start === -1) start = text.indexOf(NAME_OPEN)
  if (start === -1) return null
  const command = parseSlashCommand(text.slice(start))
  if (!command) return null
  return { before: text.slice(0, start), command, injected: text.slice(start) }
}
