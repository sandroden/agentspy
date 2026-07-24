---
type: Design Note
title: Skill and slash-command recognition
description: How agentspy detects and quantifies skill usage in data it already captures — tool badge, turn trigger and a measure of the injected context.
tags: [skill, commands, context, teaching]
timestamp: 2026-07-08T00:00:00Z
---

A skill leaves traces in the data agentspy already captures, at three
points, with no need for new observation channels:

1. **`Skill` tool** — when the model invokes it: the response of a
   [round trip](/architecture.md) contains a `tool_use` block with
   `name: "Skill"` and `input: {skill, args}`. The timeline badge shows
   🎓 with the skill name (icon in `utils/toolIcon.ts`, hint from the
   backend `AgentRuntime.tool_hint`, which for `Skill` reads
   `input.skill`).
2. **Slash-command** (`/okf:okf …`) — when the user types it: Claude Code
   expands the command *inside the user message* as a wrapper
   `<command-message>` / `<command-name>` / `<command-args>` followed by
   the **body of the SKILL.md injected verbatim**. It is a real,
   measurable context cost.
3. **Indirect Reads** — skills with reference files also show up as
   normal `Read` calls on paths containing `/skills/`.

# What the UI shows

- **Timeline, Tools column**: 🎓 badge for the `Skill`-type `tool_use`
  (point 1).
- **Timeline, turn trigger**: if the turn is opened by a slash-command,
  the Trigger column shows `🎓 Command /okf:okf` (teal) instead of
  `🧑 You`. Detection is in `utils/command.ts` (`parseSlashCommand`),
  which recognizes both the expanded wrapper and the raw form
  `/name args` that the `UserPromptSubmit` hook carries.
- **DetailPanel, Request tab**: the injected SKILL.md body is rendered by
  `SystemReminderText` as a segment of its own (`splitCommandInjection`),
  with the same scheme as the `<system-reminder>` blocks: a teal box in
  the expanded view, a `🎓 /okf:okf · N chars injected` chip in the
  compact view (click → modal). This way the user message visibly
  decomposes into its parts (real prompt, system-reminder, SKILL.md) and
  its weight in characters can be read.

# Backend snippet

`ClaudeCodeRuntime.command_snippet` (runtimes/, used by `store.py`)
cleans up the round-trip snippet when the first user message is a
slash-command: it returns `/name args` instead of the wrapper XML + the
SKILL.md, so lists and triggers stay readable even without hooks. The
logic is mirrored on the client side in `api/client.ts` (`get_event`
reconstructs the snippet).

# Limits

- The measure is in characters (a token proxy of ~char/4), consistent
  with [token accounting](/design/token-accounting.md).
- The raw form distinguishes a slash-command from free text with a
  heuristic on the first token (`/name` or `/namespace:name`); it does
  not distinguish a skill from a builtin command — it is the count of
  injected characters that makes it evident.
