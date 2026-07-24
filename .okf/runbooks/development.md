---
type: Runbook
title: Development and testing
description: Commands for backend tests, MCP wrapper tests and frontend development/build.
tags: [runbook, development, test]
timestamp: 2026-07-07T00:00:00Z
---

> The user-facing development guide is
> [`docs/development.md`](../../docs/development.md); this runbook focuses
> on the internal test/attention points.

# Commands

```bash
cd server && uv run pytest                       # collector tests (19)
cd mcp && uv run --with pytest pytest tests/     # MCP wrapper tests
cd frontend && npm run dev                       # UI hot reload (proxy → 8082)
cd frontend && npm run build                     # build served by the collector on /ui
```

# Attention points

- The delicate part is [correlation](/design/correlation.md)
  (`server/agentspy_server/correlate.py`): rules and limits are
  documented in the module docstring.
- The collector tests use as fixtures the
  [JSONL](/interfaces/jsonl-log-format.md) files already captured in
  `logs/`.
- The real hook schema was verified empirically (2026-07-07): the
  subagents' tool hooks carry `agent_id` but the parent's `session_id`.
- The DB (`agentspy.db`) and the logs stay outside the repository.
- The frontend in dev runs on Vite with a proxy to `127.0.0.1:8082`; in
  production the [collector](/components/collector-server.md) serves
  `frontend/dist` on `/ui` (explicit 404 if not built).
