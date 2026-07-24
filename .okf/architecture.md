---
type: Architecture
title: agentspy architecture
description: Single Starlette process acting as transparent proxy, collector and UI server, with three composable observation channels.
tags: [architecture, proxy, collector]
timestamp: 2026-07-07T00:00:00Z
---

agentspy is an educational tool to spy on and visualize, in real time,
the communication between Claude Code and the Anthropic API. The whole
backend is **a single Python process** (Starlette + uvicorn, managed with
uv) on port **8082**, implemented by the
[collector server](/components/collector-server.md).

```
Claude Code --ANTHROPIC_BASE_URL--> [proxy /v1/*] --forward--> api.anthropic.com
hooks       --POST /ingest/hook -->  [collector]
MCP wrapper --POST /ingest/mcp  -->      |
                                     SQLite (agentspy.db)
                                         |
frontend  <--WS /ws (live)  +  REST /api/* (replay)  +  /ui (static)
```

Routing: `/api/*`, `/ws`, `/ingest/*`, `/ui/*` handled locally;
**everything else** forwarded transparently to the upstream (Claude Code
also calls `HEAD /` and other paths: the forward must never break).

The Anthropic-specific knowledge (wire protocol) and the Claude
Code-specific knowledge (hooks, headers, artifacts) is confined to two
specializable layers — `providers/` and `runtimes/` — described in
[adapter layers](/design/adapter-layers.md).

# Observation channels

Three channels, all composable; only the first is mandatory:

1. **Proxy** (the core): captures every complete round trip — the full
   request and the response reconstructed from the SSE stream, with exact
   usage (input/output, cache read/write 5m/1h, thinking) and timing.
2. **Hooks** ([hook script](/components/hook-script.md), recommended):
   provides real session_ids, turn boundaries (UserPromptSubmit) and the
   subagent lifecycle.
3. **MCP wrapper** ([mcp wrapper](/components/mcp-wrapper.md), for MCP
   teaching): transparent stdio relay that spies on the JSON-RPC.

The three flows converge in [correlation](/design/correlation.md), which
assigns traffic to sessions/turns/subagents, and end up in the
[SQLite schema](/interfaces/sqlite-schema.md). The
[frontend](/components/frontend.md) reads via
[REST](/interfaces/rest-api.md) (replay) and
[WebSocket](/interfaces/websocket.md) (live).

# Conceptual units

- **Round trip**: one request/response to `/v1/messages`; the unit of the
  timeline.
- **Turn**: a group of round trips opened by a user prompt
  (UserPromptSubmit or heuristic).
- **Session**: a Claude Code conversation; subagents are child sessions
  (`parent_session_id`) with tokens aggregated into the parent.

# Citations

[1] Repository `README.md` — overview and quickstart.
[2] Original project plan (PLAN.md, removed 2026-07-25 — decisions kept
here) — work plan and decisions.
