# The UI

## Dashboard (home)

The entry point (`/ui/`) is a summary dashboard. A **highlighted session** (by
default the live one, or the most recent; selectable from the menu at the top
right) drives the cards and charts:

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
- **Subagents**: horizontal bars (color = model) with the tokens of each child
  session.

Every point of the charts is **clickable**: it leads to the session with the
corresponding event already selected. At the bottom, the list of sessions and
the quick-start guide.

## Session timeline

- **Vertical timeline** (time flows downward), grouped by user turn: cards for
  the round trips (model, timing, usage bar, tool badge with icon — 📄 Read, ✏️
  Edit, 💻 Bash, 🔍 Grep… — and thinking), markers for the hooks (▶ green with
  the prompt snippet for UserPromptSubmit, 🔧 with the tool name for
  Pre/PostToolUse), purple cards for MCP calls, clickable orange cards for
  subagents (child sessions, tokens aggregated into the parent). Every row has
  a colored indicator per type; the legend is at the bottom of the timeline.
- In the sidebar the **live session** is highlighted (LIVE chip, green border).
- **Time pause**: LIVE/PAUSE + back/forward scrubber over the whole history
  (space and arrow keys); data is collected regardless.
- **Context-fill**: for each round trip a stacked bar cache_read / cache_write
  / new / output — you see the context filling up and how much was served from
  the cache.

## Detail panel (right column)

Click on any event → tabbed panel: Summary | Request (full system prompt in
blocks, tools, messages) | Response (thinking, text, tool_use) | **Delta**
(what entered the context compared to the previous round) | raw JSON.

- The column is **resizable** by dragging the left border (the width is
  remembered).
- The `<system-reminder>` blocks that Claude Code inserts next to the user
  prompt have two views, switchable with the **"compact view"** checkbox in the
  header: expanded (reminders highlighted in violet, distinct from the real
  prompt) or compact (reminders reduced to "⚙ system-reminder · N char" chips;
  click on the chip → popup with the full content).

Terminology: the unit of the timeline is the *round trip* (one request/response
to `/v1/messages`); the panel shows its *payload*; inside `messages[]` each
message is made of *content blocks* (`text`, `tool_use`, `tool_result`).

## Cleaning up sessions

The **🗑 Edit** button at the top of the sidebar activates selection mode: each
session shows a checkbox and, when selecting a parent, the children (subagents)
get checked and locked because they will be deleted in cascade. The bar at the
bottom (**Delete N sessions** / **Cancel**) asks for confirmation and removes
sessions and events permanently; if you delete the open session the UI returns
to the dashboard.

From the command line:

```bash
# delete a session (with its descendants)
curl -X DELETE http://127.0.0.1:8082/api/sessions/<id>

# delete several sessions at once
curl -X POST http://127.0.0.1:8082/api/sessions/delete \
     -H 'Content-Type: application/json' -d '{"ids": ["id1", "id2"]}'
```

Both respond `{"deleted": [...]}` with the full list of removed ids (children
included). Deletion is **cascading** over child sessions and **permanent**.

## See also

- [Run tagging](run-tagging.md) — how the tag separates collections in the UI.
- [Hooks](hooks.md) — what feeds the markers and subagent structure.
- [Development](development.md) — running the UI from source with hot reload.
