---
type: API
title: WebSocket (/ws)
description: Live server→client channel for sessions and events; the client reconnects with backoff.
resource: server/agentspy_server/ws.py
tags: [api, websocket, live]
timestamp: 2026-07-07T00:00:00Z
---

A **server→client only** channel managed by `ConnectionManager` in the
[collector server](/components/collector-server.md). Requires the
`websockets` dependency (without it, uvicorn rejects the upgrade with a
404).

# Messages

| Message | When |
|---------|------|
| `{type:'hello', sessions:[...]}` | on connection open |
| `{type:'event', event:<summary>}` | new event (round trip, hook, MCP) |
| `{type:'session', session:{...}}` | session created/updated |
| `{type:'session_removed', id}` | synthetic session absorbed by a real one (merge in [correlation](/design/correlation.md)) |

The event summary is the same as the [REST API](/interfaces/rest-api.md)'s.
The incoming messages only serve to detect disconnection; the backoff
reconnection 1s→10s is in the client (`frontend/src/api/client.ts`, see
[frontend](/components/frontend.md)).
