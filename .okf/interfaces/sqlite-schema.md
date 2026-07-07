---
type: Database Schema
title: Schema SQLite (agentspy.db)
description: Due tabelle — sessions ed events — con payload JSON completi e colonne indicizzate per la timeline.
resource: server/agentspy_server/store.py
tags: [database, sqlite, schema]
timestamp: 2026-07-07T00:00:00Z
---

SQLite in modalità WAL, connessione unica condivisa con
`threading.Lock`; le chiamate da API/ingest sono spostate su thread per
non bloccare l'event loop. Percorso dal env `AGENTSPY_DB`.

# Schema

```sql
sessions(id TEXT PK,            -- session_id di Claude Code o sintetico syn-<fp>
         tag TEXT, title TEXT, model TEXT,
         parent_session_id TEXT, agent_id TEXT,   -- per subagenti
         started_at REAL, ended_at REAL, live INTEGER)

events(id INTEGER PK,
       session_id TEXT, kind TEXT,     -- round_trip | hook | mcp
       subkind TEXT,                   -- hook_event_name / <server>:<metodo>
       turn_index INTEGER, agent_id TEXT,
       ts_start REAL, ts_end REAL, ttfb_s REAL,
       model TEXT, status INTEGER, stop_reason TEXT,
       input_tokens INT, output_tokens INT,
       cache_read_tokens INT, cache_write_tokens INT,
       tool_names TEXT,                -- JSON array
       payload TEXT)                   -- JSON completo (request+response)
-- indici: (session_id, ts_start), (kind), (turn_index)
```

# Metodi chiave dello Store

- `upsert_session` — fonde `started_at=min`/`ended_at=max`, COALESCE
  sugli altri campi.
- `reassign_session` — sposta gli eventi da una sessione sintetica a
  quella reale e ne assorbe i metadati (merge della
  [correlazione](/design/correlation.md)).
- `get_sessions` — aggregati usage propri + inclusi discendenti
  ricorsivi; conta i turni con `turn_index >= 1`.
- `get_session_events` / `get_event` / `get_session_stats` — alimentano
  la [REST API](/interfaces/rest-api.md).

Il DB e i log restano fuori dal repository.
