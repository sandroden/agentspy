---
type: Design Note
title: Traffic ↔ session correlation
description: How the proxy round trips (without a session_id) are assigned to sessions, turns and subagents — the most delicate part of the backend.
resource: server/agentspy_server/correlate.py
tags: [correlation, sessions, subagents]
timestamp: 2026-07-07T00:00:00Z
---

The traffic that crosses the proxy carries no `session_id`: the
`Correlator` (in-memory state: `session_state`, `fingerprint_to_session`,
`tool_use_to_fingerprint`, `prompt_to_session`) derives it with these
rules, in order of strength:

1. **tool_use_id** — the `PreToolUse` hook carries `session_id` +
   `tool_use_id`; the previous round trip contained the `tool_use` block
   with that id (`toolu_...`) → it binds the API conversation to the hook
   session, absorbing any synthetic session (`reassign_session` +
   broadcast `session_removed`).
2. **UserPromptSubmit** — advances `turn_index += 1` authoritatively;
   from that point `has_hooks=True` and the heuristic on the user text is
   disabled. The prompt is remembered in `prompt_to_session` to bind
   conversations without tool calls.
3. **Conversation fingerprint** — sha256 of (serialized system + first
   user message + `session_key`), with `_strip_volatile` removing the
   `cache_control` markers (they move between round trips). The
   `session_key` is the header declared by the
   [runtime](/design/adapter-layers.md) (`AgentRuntime.session_id_header`;
   for Claude Code `x-claude-code-session-id`, cli >= 2.x, on every
   request, verified present 100% of the time and stable within a
   conversation): without it, two concurrent runs with the same system
   and the same first prompt would collapse into the same synthetic
   session. Same fingerprint → same session even without hooks.
4. **`x-agentspy-tag` header** — assigns the tag (see
   [run tagging](/design/run-tagging.md)).
5. **Subagents** — real schema verified empirically (2026-07-07): the
   hooks generated *inside* a subagent carry `agent_id`/`agent_type` but
   the **parent's** `session_id`; the event goes to the child session
   `sub-<agent_id>` (with `parent_session_id`), while
   `SubagentStart`/`SubagentStop` stay as markers on the parent's
   timeline.

# Degradation without hooks

Synthetic sessions `syn-<fingerprint[:12]>` and heuristic turns: a new
turn if the last user message is textual (not a `tool_result`) and the
text differs from the previous one.

# Rehydration at startup

The `Correlator` is in-memory: without rehydration a collector restart
would make `turn_index` start over from 1 (round trips renumbered and
overlapping), the hook-less round trips would create new `syn-` sessions
and the MCP/subagent joins (`tool_use_id`) would be lost. In the lifespan
(`app.py`) `Correlator.rehydrate` reconstructs from the store the
essential state of the recently active sessions (window
`AGENTSPY_REHYDRATE_HOURS`, default 48h): the maximum `turn_index` per
session, `has_hooks`, `fingerprint_to_session` and
`tool_use_to_fingerprint` recomputed from the saved payloads (fingerprint
via `fingerprint_inputs`, the same inputs as live correlation) and the
`UserPromptSubmit` prompts. The ids are the DEFINITIVE DB ones (post
merge), so the fingerprints already point to the right session. It is
best-effort: on failure it logs and starts empty.

# Known limits

- Fingerprint collisions with identical test prompts: resolved when
  `session_key` is present (header or distinct hook session_ids). Without
  the header *and* without hooks (old cli, no hooks) two identical runs
  stay indistinguishable: the proxy has no information to separate them.
- Out-of-order requests (retry / Claude Code parallelism): ordered by ts
  and out-of-order is tolerated.
- `PreCompact`/compaction: tracked as an event, but re-stitching the
  compacted conversation to the same session is not handled yet.
