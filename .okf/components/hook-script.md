---
type: Component
title: Hook script (agentspy_hook.py)
description: Fire-and-forget hook script that forwards Claude Code hook payloads to the collector; provides real session_ids and turn boundaries.
resource: hooks/agentspy_hook.py
tags: [hooks, claude-code, python]
timestamp: 2026-07-07T00:00:00Z
---

Pure stdlib Python script (only `urllib`, no heavy dependencies). Reads
stdin (JSON hook payload, fallback `{"raw": <truncated text>}`), builds
`{ts, tag, payload}` and POSTs to `AGENTSPY_URL/ingest/hook` (see
[ingest API](/interfaces/ingest-api.md)) with a **0.5s** timeout
(synchronous in the hook loop: a slow collector must not stall the
agent).

**Fire-and-forget**: it ignores any exception and always exits with
exit 0, so it never blocks Claude Code. Debug on stderr only with
`AGENTSPY_DEBUG=1`.

# Intercepted hooks

`hooks/settings-example.json` (to be copied into the observed project's
`.claude/settings.json`, replacing `/PATH/TO/agentspy`) registers 10
hooks:

`SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreToolUse` (`*`),
`PostToolUse` (`*`), `SubagentStart`, `SubagentStop`, `Stop`,
`PreCompact`, `Notification`.

From the payload the backend uses: `hook_event_name`, `session_id`,
`agent_id`/`agent_type`, `tool_use_id`, `tool_name`, `prompt`.

# Environment variables

| Variable | Default | Use |
|----------|---------|-----|
| `AGENTSPY_URL` | `http://127.0.0.1:8082` | collector endpoint |
| `AGENTSPY_TAG` | — | collection tag, see [run tagging](/design/run-tagging.md) |
| `AGENTSPY_DEBUG` | — | `1` = log to stderr |

# Role in correlation

This is the channel that gives [correlation](/design/correlation.md) the
real session_ids, the turn boundaries (UserPromptSubmit) and the subagent
lifecycle. Empirical note (2026-07-07): the tool hooks generated inside a
subagent carry `agent_id` but the parent's `session_id`.
