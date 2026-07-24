# Hooks

The hooks channel is the "registry" that gives the proxy traffic its
structure. The proxy sees *all the content* (full requests and responses) but
does not know *whose* traffic it is: HTTP requests carry no session_id, do not
distinguish a new user prompt from the automatic continuation of a tool loop,
and do not tell whether a conversation is a subagent. Hooks provide session
ids, turn boundaries and the subagent life cycle; the correlator
(`server/agentspy_server/correlate.py`) uses the two streams together.

## Setup

Copy the `hooks` section of `hooks/settings-example.json` into the
`.claude/settings.json` of the project to observe, replacing
`/PATH/TO/agentspy` with the absolute path of this checkout. The
[install scripts](installation.md) automate this into
`~/.config/agentspy/hooks.json`.

**Hooking in "on the fly"** (without touching the project settings): Claude
Code settings have no include mechanism, but the `--settings` flag loads a file
(or inline JSON) for a single invocation, with maximum priority and a merge
over the other levels. `settings-example.json` is already a complete settings
file, so — after making a copy of it with the real path in place of
`/PATH/TO/agentspy` — it is enough to:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 \
claude --settings /real/path/agentspy/hooks/settings-example.json
```

**Globally.** To observe *all* projects without repeating it on every
invocation, the same `hooks` section can live in the global user settings
`~/.claude/settings.json` (hooks there apply everywhere; a collector that is
off does not get in the way, the hook script fails silently).

## What each hook carries

| Hook | Information | Use in agentspy |
|------|-------------|-----------------|
| `SessionStart` / `SessionEnd` | real `session_id`, cwd, transcript_path | a session is born/ends in the UI, LIVE state |
| `UserPromptSubmit` | the user prompt, `session_id` | advances the turn authoritatively (timeline grouping); "binding via prompt": attaches conversations without tool calls to the real session_id; green ▶ marker with the prompt text; prompt count/marker in the dashboard |
| `PreToolUse` / `PostToolUse` | `tool_name`, `tool_use_id`, tool input/output | the strongest correlation rule: the `tool_use_id` also appears in the round trip captured by the proxy and links the API conversation to the hook session; 🔧 marker with the tool name |
| `SubagentStart` / `SubagentStop` | `agent_id`, agent type | creates the child session (`sub-<agent_id>`) with `parent_session_id`, from which: subagent blocks in the timeline, subagent bars and "incl. subagents" tokens in the dashboard |
| `Stop` | end of the response round | ■ turn-close marker |
| `PreCompact`, `Notification` | compaction, notifications | for now only tracked as events (post-compaction stitching is not yet handled) |

Every hook event also carries the tag (`AGENTSPY_TAG`) and a timestamp, and
stays visible in the timeline as a clickable marker with its full JSON payload
in the detail panel.

## The hook script

`hooks/agentspy_hook.py` is fire-and-forget (always exit 0, 2s timeout): it
reads the JSON payload that Claude Code passes on stdin, builds a payload with
timestamp, tag and the received data, and POSTs it as-is to `/ingest/hook`,
without ever blocking or slowing down the session. Any error (timeout,
connection, exception) is silently ignored.

Environment variables read by the script:

- `AGENTSPY_URL`: base URL of the server (default `http://127.0.0.1:8082`);
- `AGENTSPY_TAG`: identifying tag for the session (optional);
- `AGENTSPY_DEBUG`: if set to `1`, prints errors to stderr.

## Degraded mode (without hooks)

**It works without hooks too**, in degraded mode: the conversation fingerprint
(sha256 of system + first user message) chains the round trips of the same
conversation, and the new turn is inferred from the text of the last user
message. But the session_ids are synthetic (`syn-<fingerprint>`), subagents are
not recognized as children and the turn boundaries are heuristic: for full
educational use (following a subagent, counting the round trips of a prompt)
hooks are effectively necessary.

## See also

- [Installation](installation.md) — the install scripts that generate
  `hooks.json`.
- [Run tagging](run-tagging.md) — `AGENTSPY_TAG` and the redundant tag channels.
- [MCP wrapper](mcp-wrapper.md) — the third observation channel.
- [`.okf/components/hook-script.md`](../.okf/components/hook-script.md) —
  internal notes on the hook script.
- [`.okf/design/correlation.md`](../.okf/design/correlation.md) — how the
  correlator uses the streams together.
