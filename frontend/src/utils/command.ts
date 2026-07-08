/**
 * Riconoscere l'invocazione di una skill / slash-command in un messaggio user.
 *
 * Claude Code espande un `/namespace:name args` digitato in un blocco che
 * viene iniettato nel messaggio user:
 *
 *   <command-message>name</command-message>
 *   <command-name>/namespace:name</command-name>
 *   <command-args>args</command-args>
 *   Base directory for this skill: /…      ← qui segue lo SKILL.md iniettato
 *   # …corpo della skill…
 *
 * Quel corpo iniettato è costo di contesto reale: mostrarlo (e misurarlo) è
 * lo scopo didattico. Una skill invocata dal modello, invece, appare come un
 * `tool_use` di nome `Skill` — gestito da toolIcon(); qui trattiamo solo la
 * forma slash-command.
 */

const NAME_RE = /<command-name>\s*([\s\S]*?)\s*<\/command-name>/
const ARGS_RE = /<command-args>\s*([\s\S]*?)\s*<\/command-args>/
const MSG_OPEN = '<command-message>'
const NAME_OPEN = '<command-name>'
// Forma "grezza" (quella che porta l'hook UserPromptSubmit): "/name" o
// "/namespace:name" come primo token, seguito da spazio o fine. Il lookahead
// evita falsi positivi su path ("/tmp/foo", "/home/sandro").
const RAW_RE = /^\/([A-Za-z][\w-]*(?::[\w-]+)?)(?=\s|$)([^\n]*)/

export interface SlashCommand {
  name: string // es. "/okf:okf" (slash iniziale mantenuto)
  args: string // es. "produce .okf" ("" se assenti)
}

/** Rileva uno slash-command sia nella forma espansa (wrapper) sia in quella
 *  grezza "/name args" (il testo che porta l'hook UserPromptSubmit). */
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
  before: string // testo user prima del wrapper (può essere '')
  command: SlashCommand
  injected: string // wrapper + corpo skill iniettato (il costo di contesto)
}

/** Per il pannello di dettaglio: separa un blocco testo che porta il wrapper
 *  espanso nel testo user precedente e nel blocco iniettato. Restituisce null
 *  quando non c'è un wrapper espanso (la forma grezza "/name" non inietta). */
export function splitCommandInjection(text: string): CommandInjection | null {
  if (!text) return null
  let start = text.indexOf(MSG_OPEN)
  if (start === -1) start = text.indexOf(NAME_OPEN)
  if (start === -1) return null
  const command = parseSlashCommand(text.slice(start))
  if (!command) return null
  return { before: text.slice(0, start), command, injected: text.slice(start) }
}
