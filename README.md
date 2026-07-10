# agentspy

An educational tool to **spy on and visualize in real time** the
communication between Claude Code and the Anthropic API: how each request is
composed (system prompt, tools, messages), what the model replies (usage,
cache, thinking, tool use), and how subagents and MCP servers work.

<img width="3430" height="1891" alt="immagine" src="https://github.com/user-attachments/assets/46759bdb-6752-4748-b662-3cbaa96fb59d" />

## Architecture

```
Claude Code --ANTHROPIC_BASE_URL--> [proxy /v1/*] --forward--> api.anthropic.com
hooks       --POST /ingest/hook -->  [collector]
wrapper MCP --POST /ingest/mcp  -->      |
                                     SQLite (agentspy.db)
                                         |
frontend  <--WS /ws (live)  +  REST /api/* (replay)  +  /ui (static)
```

A single process (`server/`, Starlette+uvicorn via uv) acts as a
transparent proxy, collects everything into SQLite and serves the UI. Three
observation channels, all optional and composable:

1. **Proxy** (mandatory, the core): captures every complete round trip — the
   full request and the response reconstructed from the SSE stream, with
   exact usage (input/output, cache read/write 5m/1h, thinking) and timing.
2. **Hooks** (recommended): provides real session_ids, turn boundaries
   (UserPromptSubmit) and the subagent life cycle.
3. **MCP wrapper** (for MCP teaching): a transparent stdio relay that spies
   on the JSON-RPC (initialize, tools/list, tools/call).

## Quick start

```bash
# 1. the collector (port 8082)
cd server && uv run agentspy

# 2. Claude Code through the proxy
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude

# 3. the UI
xdg-open http://127.0.0.1:8082/ui/
```

Note: if `ANTHROPIC_API_KEY` is present in the environment it takes
precedence over the claude.ai login: `env -u ANTHROPIC_API_KEY
ANTHROPIC_BASE_URL=... claude`.

### Install (the `claude-spy` shell function)

`install.sh` (Linux/macOS) and `install.ps1` (Windows PowerShell) automate
the steps above: they generate `~/.config/agentspy/hooks.json` from
`hooks/settings-example.json` (with the real path to this checkout in place
of `/PATH/TO/agentspy`) and add a `claude-spy [tag]` function to your shell
so a session is spied on with one command:

```bash
git clone <this repo> && cd agentspy
bash install.sh          # or: chmod +x install.sh && ./install.sh
# open a new shell (or: source ~/.bashrc / ~/.zshrc)

cd agentspy && just up
cd my-project-to-spy
claude-spy my-tag
```

On Windows:

```powershell
.\install.ps1
# open a new PowerShell (or: . $PROFILE)
```

Both scripts are idempotent (safe to re-run) and reversible
(`install.sh --uninstall` / `install.ps1 -Uninstall`); `--no-rc` / `-NoRc`
writes `hooks.json` only and prints the function instead of touching your
shell config. `install.ps1` is community-contributed and not covered by CI
on Windows — please report issues.

### Trying the UI without real traffic

`scripts/seed_demo.py` generates a demo DB (a live session with tool use, a
subagent and an MCP event + a short closed session), useful to explore the
dashboard and panels without spending tokens:

```bash
cd server
AGENTSPY_DB=./agentspy-demo.db uv run python ../scripts/seed_demo.py
AGENTSPY_DB=./agentspy-demo.db uv run agentspy
```

### Tagging runs (to compare strategies)

```bash
ANTHROPIC_CUSTOM_HEADERS='x-agentspy-tag: con-okf' \
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 AGENTSPY_TAG=con-okf claude
```

The two variables carry the **same tag over two different channels**, and
converge on the same session `tag` field:

- `ANTHROPIC_CUSTOM_HEADERS` travels with the API traffic: Claude Code adds
  the `x-agentspy-tag` header to every request and the proxy applies it to
  the session it attributes the round trip to;
- `AGENTSPY_TAG` travels with the hooks: the script reads it from the
  environment and sends it to `/ingest/hook` (it also reaches the child
  sessions of subagents).

At steady state one is enough, as long as its channel is active: without
installed hooks the header is needed; with the proxy in the middle (always,
when spying) the header alone is sufficient. Setting both is zero-cost
redundancy that covers the edge cases: the header also tags processes that
inherit the environment but have no hooks (e.g. a `claude -p` launched by an
automation), the env also tags hook events of traffic not yet attributed by
the correlator.

In the UI the tag distinguishes the collections; every session has its own
URL (`/ui/session/<id>`), so two runs open in two browser tabs.

### Hooks

Copy the `hooks` section of `hooks/settings-example.json` into the
`.claude/settings.json` of the project to observe, replacing
`/PATH/TO/agentspy`. Variables: `AGENTSPY_URL`, `AGENTSPY_TAG`,
`AGENTSPY_DEBUG`. The script is fire-and-forget (always exit 0, 2s timeout):
it reads the JSON payload that Claude Code passes on stdin and forwards it
as-is to `/ingest/hook`, without ever blocking or slowing down the session.

**Hooking in "on the fly"** (without touching the project settings): Claude
Code settings have no include mechanism, but the `--settings` flag loads a
file (or inline JSON) for a single invocation, with maximum priority and a
merge over the other levels. `settings-example.json` is already a complete
settings file, so — after making a copy of it with the real path in place of
`/PATH/TO/agentspy` — it is enough to:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 \
claude --settings /real/path/agentspy/hooks/settings-example.json
```

Alternatively, to observe *all* projects without repeating it on every
invocation, the same `hooks` section can live in the global user settings
`~/.claude/settings.json` (hooks there apply everywhere; a collector that is
off does not get in the way, the hook script fails silently).

**Global role.** The proxy sees *all the content* (full requests and
responses) but does not know *whose* traffic it is: HTTP requests do not
carry a session_id, do not distinguish a new user prompt from the automatic
continuation of a tool loop, and do not tell whether a conversation is a
subagent. Hooks are the "registry" channel that provides this structure; the
correlator (`server/agentspy_server/correlate.py`) uses the two streams
together: without hooks the sessions stay synthetic (`syn-<fingerprint>`)
with heuristic turns, with hooks they become real sessions with exact turn
boundaries.

What each hook carries:

| Hook | Information | Use in agentspy |
|---|---|---|
| `SessionStart` / `SessionEnd` | real `session_id`, cwd, transcript_path | a session is born/ends in the UI, LIVE state |
| `UserPromptSubmit` | the user prompt, `session_id` | advances the turn authoritatively (timeline grouping); "binding via prompt": attaches conversations without tool calls to the real session_id; green ▶ marker with the prompt text; prompt count/marker in the dashboard |
| `PreToolUse` / `PostToolUse` | `tool_name`, `tool_use_id`, tool input/output | the strongest correlation rule: the `tool_use_id` also appears in the round trip captured by the proxy and links the API conversation to the hook session; 🔧 marker with the tool name |
| `SubagentStart` / `SubagentStop` | `agent_id`, agent type | creates the child session (`sub-<agent_id>`) with `parent_session_id`, from which: subagent blocks in the timeline, subagent bars and "incl. subagents" tokens in the dashboard |
| `Stop` | end of the response round | ■ turn-close marker |
| `PreCompact`, `Notification` | compaction, notifications | for now only tracked as events (post-compaction stitching is not yet handled) |

Every hook event also carries the tag (`AGENTSPY_TAG`) and a timestamp, and
stays visible in the timeline as a clickable marker with its full JSON
payload in the detail panel.

**It works without hooks too**, in degraded mode: the conversation
fingerprint (sha256 of system + first user message) chains the round trips
of the same conversation, and the new turn is inferred from the text of the
last user message. But the session_ids are synthetic, subagents are not
recognized as children and the turn boundaries are heuristic: for full
educational use (following a subagent, counting the round trips of a prompt)
hooks are effectively necessary.

### MCP wrapper

In the MCP config replace the server command with the wrapper:

```json
{"mcpServers": {"eco": {
  "command": "/path/agentspy/mcp/agentspy_mcp_wrapper.py",
  "args": ["--name", "eco", "--", "real-server-command", "arg1"]
}}}
```

The `tools/call` are attached to the right session via the
`claudecode/toolUseId` that Claude Code passes in `params._meta`.

## The UI

### Dashboard (home)

The entry point (`/ui/`) is a summary dashboard. A **highlighted session**
(by default the live one, or the most recent; selectable from the menu at
the top right) drives cards and charts:

- **Metric cards**: peak context, total tokens consumed ("integral"),
  consumption/peak ratio, user prompts, round trips, subagents with their
  tokens, API cost estimate (pricing per model family, real data only — no
  hypothetical projection).
- **Context per round trip**: one line per session (the highlighted one in
  blue, the others dimmed), green markers on round trips opened by a user
  prompt, red line of the ~200k ceiling when the scale justifies it.
- **What the context is made of**: stacked area of cache_read / cache_write /
  new input / output.
- **Cumulative consumption**: the integral of the tokens; **by dragging with
  the mouse** you select an interval and read the tokens and cost of that
  stretch.
- **Subagents**: horizontal bars (color = model) with the tokens of each
  child session.

Every point of the charts is **clickable**: it leads to the session with the
corresponding event already selected. At the bottom, the list of sessions
and the quick-start guide.

### Session timeline

- **Vertical timeline** (time flows downward), grouped by user turn: cards
  for the round trips (model, timing, usage bar, tool badge with icon — 📄
  Read, ✏️ Edit, 💻 Bash, 🔍 Grep… — and thinking), markers for the hooks (▶
  green with the prompt snippet for UserPromptSubmit, 🔧 with the tool name
  for Pre/PostToolUse), purple cards for MCP calls, clickable orange cards
  for subagents (child sessions, tokens aggregated into the parent). Every
  row has a colored indicator per type; the legend is at the bottom of the
  timeline.
- In the sidebar the **live session** is highlighted (LIVE chip, green
  border).
- **Time pause**: LIVE/PAUSE + back/forward scrubber over the whole history
  (space and arrow keys); data is collected regardless.
- **Context-fill**: for each round trip a stacked bar cache_read /
  cache_write / new / output — you see the context filling up and how much
  was served from the cache.

### Detail panel (right column)

Click on any event → tabbed panel: Summary | Request (full system prompt in
blocks, tools, messages) | Response (thinking, text, tool_use) | **Delta**
(what entered the context compared to the previous round) | raw JSON.

- The column is **resizable** by dragging the left border (the width is
  remembered).
- The `<system-reminder>` blocks that Claude Code inserts next to the user
  prompt have two views, switchable with the **"compact view"** checkbox in
  the header: expanded (reminders highlighted in violet, distinct from the
  real prompt) or compact (reminders reduced to "⚙ system-reminder · N char"
  chips; click on the chip → popup with the full content).

Terminology: the unit of the timeline is the *round trip* (one
request/response to `/v1/messages`); the panel shows its *payload*; inside
`messages[]` each message is made of *content blocks* (`text`, `tool_use`,
`tool_result`).

### Cleaning up sessions

The **🗑 Edit** button at the top of the sidebar activates selection mode:
each session shows a checkbox and, when selecting a parent, the children
(subagents) get checked and locked because they will be deleted in cascade.
The bar at the bottom (**Delete N sessions** / **Cancel**) asks for
confirmation and removes sessions and events permanently; if you delete the
open session the UI returns to the dashboard.

From the command line:

```bash
# delete a session (with its descendants)
curl -X DELETE http://127.0.0.1:8082/api/sessions/<id>

# delete several sessions at once
curl -X POST http://127.0.0.1:8082/api/sessions/delete \
     -H 'Content-Type: application/json' -d '{"ids": ["id1", "id2"]}'
```

Both respond `{"deleted": [...]}` with the full list of removed ids
(children included). Deletion is **cascading** over child sessions and
**permanent**.

## Development

```bash
cd server && uv run pytest          # collector tests (40+)
cd mcp && uv run --with pytest pytest tests/   # MCP wrapper tests
cd frontend && npm run dev          # UI with hot reload (proxy to 8082)
cd frontend && npm run build        # build served by the collector on /ui
```

The traffic↔sessions correlation (the delicate part) is in
`server/agentspy_server/correlate.py`, with the rules and limits documented
in the docstring. Real hook schema verified empirically (2026-07-07): the
subagent tool hooks carry `agent_id` but the parent's `session_id`.

## Known limitations / next steps

- Per-component token estimate (system/tools/messages) via characters/4; the
  real (exact) usage comes from the API response.
- The "classic" chart (time on the x-axis) is planned as an optional view,
  not yet implemented.
- Side-by-side comparison of two runs: for now two browser tabs.
- `PreCompact`/compaction: tracked as an event, the re-stitching of the
  compacted conversation to the same session is not yet handled.
