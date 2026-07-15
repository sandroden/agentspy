---
type: Design Note
title: Riconoscimento di skill e slash-command
description: Come agentspy individua e quantifica l'uso di una skill nei dati già catturati — badge tool, trigger di turno e misura del contesto iniettato.
tags: [skill, comandi, contesto, didattica]
timestamp: 2026-07-08T00:00:00Z
---

Una skill lascia tracce nei dati che agentspy già cattura, in tre punti,
senza bisogno di nuovi canali di osservazione:

1. **Tool `Skill`** — quando è il modello a invocarla: nella risposta di
   un [round trip](/architecture.md) c'è un blocco `tool_use` con
   `name: "Skill"` e `input: {skill, args}`. Il badge in timeline mostra
   🎓 col nome della skill (icona in `utils/toolIcon.ts`, hint dal
   backend `AgentRuntime.tool_hint`, che per `Skill` legge `input.skill`).
2. **Slash-command** (`/okf:okf …`) — quando la digita l'utente: Claude
   Code espande il comando *dentro il messaggio user* come wrapper
   `<command-message>` / `<command-name>` / `<command-args>` seguito dal
   **corpo dello SKILL.md iniettato verbatim**. È costo di contesto
   reale e misurabile.
3. **Read indiretti** — le skill con file di riferimento si manifestano
   anche come normali `Read` su path che contengono `/skills/`.

# Cosa mostra la UI

- **Timeline, colonna Tools**: badge 🎓 per il `tool_use` di tipo
  `Skill` (punto 1).
- **Timeline, trigger del turno**: se il turno è aperto da uno
  slash-command, la colonna Trigger mostra `🎓 Command /okf:okf` (teal)
  invece di `🧑 You`. La rilevazione è in `utils/command.ts`
  (`parseSlashCommand`), che riconosce sia il wrapper espanso sia la
  forma grezza `/nome args` che porta l'hook `UserPromptSubmit`.
- **DetailPanel, tab Richiesta**: il corpo SKILL.md iniettato è reso da
  `SystemReminderText` come segmento a sé (`splitCommandInjection`),
  con lo stesso schema dei `<system-reminder>`: box teal in vista
  espansa, chip `🎓 /okf:okf · N char iniettati` in vista compatta
  (click → modal). Così il messaggio user si scompone visibilmente nelle
  sue parti (prompt reale, system-reminder, SKILL.md) e se ne legge il
  peso in caratteri.

# Snippet backend

`ClaudeCodeRuntime.command_snippet` (runtimes/, usato da `store.py`)
pulisce lo snippet del round trip quando
il primo messaggio user è uno slash-command: restituisce `/nome args`
invece dell'XML del wrapper + lo SKILL.md, così liste e trigger restano
leggibili anche senza hook. La logica è rispecchiata lato client in
`api/client.ts` (`get_event` ricostruisce lo snippet).

# Limiti

- La misura è in caratteri (proxy dei token ~char/4), coerente con la
  [contabilità dei token](/design/token-accounting.md).
- La forma grezza distingue uno slash-command da testo libero con
  un'euristica sul primo token (`/nome` o `/namespace:nome`); non
  distingue una skill da un comando builtin — è il conteggio dei
  caratteri iniettati a renderlo evidente.
