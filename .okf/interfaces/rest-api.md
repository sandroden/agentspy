---
type: API
title: REST API (/api/*)
description: Read-only REST endpoints used by the frontend for replay and lazy detail.
resource: server/agentspy_server/api.py
tags: [api, rest, backend]
timestamp: 2026-07-07T00:00:00Z
---

Served by the [collector server](/components/collector-server.md) on
`http://127.0.0.1:8082`.

# Endpoints

| Endpoint | Response |
|----------|----------|
| `GET /api/sessions` | Session list with aggregates: own tokens **and** including subagents, duration, turn count, round trips, live, tag. |
| `GET /api/sessions/{id}/events` | Lightweight event summaries (without payload), ordered by `ts_start`. |
| `GET /api/events/{id}` | Full event row with the complete payload (lazy-loaded on click). 404 if absent. |
| `GET /api/events/{id}/artifact?key=<kind>\|<path>` | Content of a single context artifact of that round trip (`{kind, label, path, media_type, format, content, images, chars}`), read on demand. 400 without `key`, 404 if the artifact is not in that body. |
| `GET /api/sessions/{id}/stats` | Per-round-trip series (real tokens + char estimates of system/tools/messages) for the context-fill. |

# Event summary

```
{id, kind, subkind, session_id, turn_index, agent_id,
 ts_start, duration_s, ttfb_s, model, status, stop_reason,
 usage{...}, tool_names, snippet}
```

The data comes from the [SQLite schema](/interfaces/sqlite-schema.md);
the equivalent live channel is the [WebSocket](/interfaces/websocket.md).
