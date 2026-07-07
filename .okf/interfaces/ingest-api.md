---
type: API
title: Ingest API (/ingest/*)
description: Endpoint di ingestione per gli eventi degli hook di Claude Code e del wrapper MCP.
resource: server/agentspy_server/ingest.py
tags: [api, ingest, hooks, mcp]
timestamp: 2026-07-07T00:00:00Z
---

Due endpoint POST sul [collector server](/components/collector-server.md).

# POST /ingest/hook

Riceve `{ts, tag, payload}` dallo
[hook script](/components/hook-script.md). Flusso:

1. correla via `correlate_hook` (vedi [correlazione](/design/correlation.md));
2. gestisce il merge di sessioni sintetiche (`reassign_session` +
   broadcast `session_removed` sul [WebSocket](/interfaces/websocket.md));
3. upserta le sessioni figlie dei subagenti;
4. chiude la sessione su `Stop`/`SubagentStop`;
5. salva l'evento con `kind='hook'`, `subkind=<hook_event_name>` e fa
   broadcast.

Risponde `{ok, event_id, session_id}`.

# POST /ingest/mcp

Riceve dal [wrapper MCP](/components/mcp-wrapper.md) frame JSON-RPC
accoppiati request↔response. Se manca il `session_id` lo ricava da
`params._meta["claudecode/toolUseId"]` via `session_for_tool_use`.
Salva con `kind='mcp'`, `subkind="<server>:<method>"`. Gli eventi di
lifecycle (initialize, tools/list) restano senza sessione.
