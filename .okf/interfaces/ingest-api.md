---
type: API
title: Ingest API (/ingest/*)
description: Ingestion endpoints for Claude Code hook events and the MCP wrapper.
resource: server/agentspy_server/ingest.py
tags: [api, ingest, hooks, mcp]
timestamp: 2026-07-07T00:00:00Z
---

Two POST endpoints on the [collector server](/components/collector-server.md).

# POST /ingest/hook

Receives `{ts, tag, payload}` from the
[hook script](/components/hook-script.md). Flow:

1. correlate via `correlate_hook` (see [correlation](/design/correlation.md));
2. handle the synthetic-session merge (`reassign_session` + broadcast
   `session_removed` on the [WebSocket](/interfaces/websocket.md));
3. upsert the subagents' child sessions;
4. close the session on `Stop`/`SubagentStop`;
5. save the event with `kind='hook'`, `subkind=<hook_event_name>` and
   broadcast.

Responds `{ok, event_id, session_id}`.

# POST /ingest/mcp

Receives from the [MCP wrapper](/components/mcp-wrapper.md) request↔response
paired JSON-RPC frames. If the `session_id` is missing it derives it from
`params._meta["claudecode/toolUseId"]` via `session_for_tool_use`. Saves
with `kind='mcp'`, `subkind="<server>:<method>"`. Lifecycle events
(initialize, tools/list) remain without a session.
