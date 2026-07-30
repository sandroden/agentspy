---
type: Database Schema
title: SQLite schema (agentspy.db)
description: Two tables — sessions and events — with full JSON payloads and indexed columns for the timeline.
resource: server/agentspy_server/store.py
tags: [database, sqlite, schema]
timestamp: 2026-07-07T00:00:00Z
---

SQLite in WAL mode, a single shared connection with `threading.Lock`;
calls from API/ingest are moved onto threads so as not to block the event
loop. Path from the `AGENTSPY_DB` env.

# Schema

```sql
sessions(id TEXT PK,            -- Claude Code session_id or synthetic syn-<fp>
         tag TEXT, title TEXT, model TEXT,
         parent_session_id TEXT, agent_id TEXT,   -- for subagents
         started_at REAL, ended_at REAL, live INTEGER,
         cwd TEXT)                     -- session working dir

events(id INTEGER PK,
       session_id TEXT, kind TEXT,     -- round_trip | hook | mcp
       subkind TEXT,                   -- hook_event_name / <server>:<method>
       turn_index INTEGER, agent_id TEXT,
       ts_start REAL, ts_end REAL, ttfb_s REAL,
       model TEXT, status INTEGER, stop_reason TEXT,
       input_tokens INT, output_tokens INT,
       cache_read_tokens INT, cache_write_tokens INT,
       cache_write_5m_tokens INT,      -- cache write split by TTL; NULL when
       cache_write_1h_tokens INT,      -- the provider doesn't report the tier
       tool_names TEXT,                -- JSON array
       payload TEXT,                   -- full JSON (request+response)
       dedup_key TEXT)                 -- idempotent natural key (sha256)
-- indexes: (session_id, ts_start), (kind), (turn_index)
-- UNIQUE(dedup_key): idx_events_dedup
```

# Event idempotency

`dedup_key` = `sha256(session_id | kind | subkind | ts_start | ts_end |
payload)` with the payload ALREADY serialized (not re-serialized, so the
backfill key matches the insert key). Only byte-identical events collide;
two distinct but close events (e.g. two `PreToolUse` in the same ms) have
different payloads and stay separate. `insert_event` uses `INSERT OR
IGNORE` and on conflict returns the existing id: re-ingest/re-seed/replay
of the same event do not double-count the aggregated tokens.

The migration (`_migrate_dedup_key_locked`, at store startup) is additive
and idempotent: `ALTER TABLE` guarded by `PRAGMA table_info`, backfill of
the rows with `dedup_key NULL`, `CREATE UNIQUE INDEX IF NOT EXISTS`. Only
if byte-identical rows already duplicated emerge are the copies removed,
keeping the `MIN(id)` (a logged action; on the live DB there are 0).
Verified on a copy of a real DB: no rows removed.

# Cache-TTL migration

`_migrate_cache_tiers_locked` (same startup, same pattern) adds
`cache_write_5m_tokens` / `cache_write_1h_tokens` and backfills them from
`payload -> response.usage.cache_creation`, which has always carried the
tier: nothing is invented, the value was simply not promoted to a column.
Restricted to `kind='round_trip'` with both columns still NULL (idempotent,
negligible on later starts), and guarded by `json_valid(payload)` because
`json_extract` on malformed text raises instead of returning NULL. Measured
on a copy of the live DB (155 MB, 471 round trips): ~2 s, 0 rows where
`cache_write_tokens != 5m + 1h`. NULL is preserved as "tier unknown" —
never flattened to 0 — see [token accounting](/design/token-accounting.md).

# Key Store methods

- `upsert_session` — merges `started_at=min`/`ended_at=max`, COALESCE on
  the other fields.
- `reassign_session` — moves the events from a synthetic session to the
  real one and absorbs its metadata (the [correlation](/design/correlation.md)
  merge).
- `get_sessions` — own usage aggregates + including recursive
  descendants; counts the turns with `turn_index >= 1`.
- `get_session_events` / `get_event` / `get_session_stats` — feed the
  [REST API](/interfaces/rest-api.md).

The DB and the logs stay outside the repository.
