---
type: Data Format
title: JSONL format of the standalone proxy logs
description: One JSON record per line for each round trip, captured back then by the standalone prototype (now removed); the files in logs/ remain as test fixtures.
resource: logs/
tags: [jsonl, log, data-format]
timestamp: 2026-07-07T00:00:00Z
---

Produced back then by the standalone prototype `agentspy_proxy.py`
(removed on 2026-07-16) into files `logs/run-<YYYYMMDD-HHMMSS>.jsonl` —
**not** used by the server, which writes to
[SQLite](/interfaces/sqlite-schema.md). The captured JSONL files serve as
fixtures for the collector tests.

# Record schema

- Top-level: `id` (counter), `ts` (ISO UTC), `method`, `path`, `query`,
  `status`, `timing` (`{ttfb_s, total_s}`), `request`, `response`.
- `request`: `headers` (with `authorization`/`x-api-key`/`cookie` →
  `<redacted>`), `analysis`
  (`{model, stream, max_tokens, system_chars, tools:{count,chars,names},
  messages:{count,chars,roles}}`), `body` (the full request:
  system/tools/messages).
- `response`, by type:
  - `type:"sse"` — 200 stream: reconstructed `message`, `usage`,
    `stop_reason`, `events_count`, `content_summary`;
  - `type:"json"` — non-stream responses (400/401, count_tokens);
  - `type:"raw"` — HEAD/404.
- With `AGENTSPY_SAVE_RAW=1` it also includes `raw_events` (raw SSE).
