---
type: Component
title: opencode plugin (hooks/opencode)
description: JS plugin for opencode that translates the runtime's native events into the neutral ingest API format; counterpart of the Claude Code hook script.
resource: hooks/opencode
tags: [opencode, plugin, hooks, ingest]
timestamp: 2026-07-16T00:00:00Z
---

The opencode counterpart of the Claude Code
[hook script](/components/hook-script.md): `agentspy.js` is an ESM plugin
that opencode loads in-process (via the `plugin` field of `opencode.json`
or from `.opencode/plugin/`) and that POSTs events to
`POST /ingest/hook` — fire-and-forget, 500ms timeout, never propagate
errors to the agent.

It translates the native events into the neutral ingest format
([runtime layer boundary](/design/adapter-layers.md)): the
`hook_event_name` values stay opencode's NATIVE names (`chat.message`,
`tool.execute.before/after`, `session.idle`), declared in the
`OpencodeRuntime` vocabulary
(`server/agentspy_server/runtimes/opencode.py`).

Facts verified in E2E (2026-07-16, opencode 1.18):

- the tool hooks' `callID` **is** the Anthropic-wire `toolu_…` → the
  `tool_use_id → session` join works as with Claude Code;
- correlation produces a single session `ses_…` (prompt-binding + join),
  with no HTTP session header;
- opencode injects the instructions into the **system prompt** as a
  single concatenated block with `Instructions from: <path>` markers
  (AGENTS.md **and** `~/.claude/CLAUDE.md`), followed by the
  skills/mcp/references sections: the extractor
  (`runtimes/opencode_artifacts.py`) splits them out by span up to the
  start of a known section;
- config: `provider.anthropic.options.baseURL` must include `/v1`.

Current limits in `hooks/opencode/README.md` (subagents via `parentID`
not correlated, MCP `_meta` not observed). Auth: metered API key only
(OAuth Pro/Max tokens in third-party tools violate the Anthropic ToS
2026).

# Citations

[1] `hooks/opencode/README.md` — installation and limits.
[2] `hooks/opencode/agentspy.js` — implementation.
