---
type: Data Format
title: Formato JSONL dei log del proxy standalone
description: Un record JSON per riga per ogni round trip catturato dal prototipo agentspy_proxy.py; usato come fixture nei test.
resource: logs/
tags: [jsonl, log, formato-dati]
timestamp: 2026-07-07T00:00:00Z
---

Prodotto dal [proxy standalone](/components/standalone-proxy.md) in file
`logs/run-<YYYYMMDD-HHMMSS>.jsonl` — **non** usato dal server, che
scrive su [SQLite](/interfaces/sqlite-schema.md). I JSONL catturati
servono da fixture per i test del collector.

# Schema del record

- Top-level: `id` (contatore), `ts` (ISO UTC), `method`, `path`,
  `query`, `status`, `timing` (`{ttfb_s, total_s}`), `request`,
  `response`.
- `request`: `headers` (con `authorization`/`x-api-key`/`cookie` →
  `<redacted>`), `analysis`
  (`{model, stream, max_tokens, system_chars, tools:{count,chars,names},
  messages:{count,chars,roles}}`), `body` (richiesta integrale:
  system/tools/messages).
- `response`, per tipo:
  - `type:"sse"` — stream 200: `message` ricostruito, `usage`,
    `stop_reason`, `events_count`, `content_summary`;
  - `type:"json"` — risposte non-stream (400/401, count_tokens);
  - `type:"raw"` — HEAD/404.
- Con `AGENTSPY_SAVE_RAW=1` include anche `raw_events` (SSE grezzi).
