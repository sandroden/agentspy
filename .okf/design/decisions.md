---
type: Decision Record
title: Architectural decisions (2026-07-07)
description: Decisions taken with Sandro at the start of the project — stack, storage, timeline UX — and things explicitly deferred.
tags: [decisions, architecture]
timestamp: 2026-07-07T00:00:00Z
---

Decisions taken with Sandro on 2026-07-07 (source: the original project
plan, PLAN.md, removed 2026-07-25 — decisions kept here):

- **Frontend**: plain Vue 3 + Vite (Pinia, TS, custom timeline
  rendering, no chart library for the MVP).
- **Storage**: SQLite (full payloads + indexed columns) — see
  [schema](/interfaces/sqlite-schema.md).
- **Single process**: proxy + collector + UI in one Python process on
  port 8082 — see [architecture](/architecture.md).
- **Vertical timeline** (time flows downward); the classic charts
  (x-axis = time) only as a future optional view.
- **No synchronized side-by-side comparison**; each session has its own
  URL so two sessions open in two tabs. Comparing runs goes through the
  [collection tags](/design/run-tagging.md).
- **Time pause**: LIVE ↔ PAUSE with a scrubber over the whole history;
  data is collected anyway, always. While paused the session metrics
  (tokens, cost, peak context) follow the playhead instead of showing the
  final totals — see [frontend](/components/frontend.md).
- **Multi-session**: one at a time in the timeline, a sidebar with the
  list; subagents nested in the parent, clickable, with aggregated
  totals.
- **Click on any event** → detail panel with the full payload.

# Deferred / not in the MVP

- Precise per-component token estimate (`count_tokens` endpoint) — today
  char/4, see [token accounting](/design/token-accounting.md).
- Classic chart with time on the x-axis (optional view).
- Side-by-side comparison of two runs.
- Re-stitching the conversation after `PreCompact`/compaction.
- Advanced animations (flows, elaborate transitions).

# Citations

[1] Original project plan (PLAN.md, removed 2026-07-25 — decisions kept
here), section "Decisions taken with Sandro".
