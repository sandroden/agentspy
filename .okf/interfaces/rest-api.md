---
type: API
title: REST API (/api/*)
description: Endpoint REST read-only usati dal frontend per replay e dettaglio lazy.
resource: server/agentspy_server/api.py
tags: [api, rest, backend]
timestamp: 2026-07-07T00:00:00Z
---

Serviti dal [collector server](/components/collector-server.md) su
`http://127.0.0.1:8082`.

# Endpoint

| Endpoint | Risposta |
|----------|----------|
| `GET /api/sessions` | Elenco sessioni con aggregati: token propri **e** inclusi subagenti, durata, n. turni, round trip, live, tag. |
| `GET /api/sessions/{id}/events` | Event summary leggeri (senza payload), ordinati per `ts_start`. |
| `GET /api/events/{id}` | Riga evento completa con payload integrale (caricato lazy al click). 404 se assente. |
| `GET /api/sessions/{id}/stats` | Serie per round trip (token reali + stime char di system/tools/messages) per il context-fill. |

# Event summary

```
{id, kind, subkind, session_id, turn_index, agent_id,
 ts_start, duration_s, ttfb_s, model, status, stop_reason,
 usage{...}, tool_names, snippet}
```

I dati provengono dallo [schema SQLite](/interfaces/sqlite-schema.md);
il canale live equivalente è il [WebSocket](/interfaces/websocket.md).
