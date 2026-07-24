---
type: Script
title: Seed demo (seed_demo.py)
description: Generates a demo DB to explore the UI without real traffic or token consumption.
resource: scripts/seed_demo.py
tags: [demo, tooling]
timestamp: 2026-07-07T00:00:00Z
---

Imports `Store` and `analyze_request_body` from `agentspy_server` (adds
`../server` to `sys.path`), drops and recreates the DB pointed to by
`AGENTSPY_DB` (default `./agentspy-demo.db`) and populates it with 3
sessions:

- **A** (live, featured, tag `demo-live`): 4 turns with real prompts,
  2-3 round trips per turn, various tool uses, complete hooks, an
  `Explore` subagent (child session, sonnet model) and an MCP event
  `context7:query-docs`.
- The subagent's **child** session.
- **B** (closed, short, tag `demo-breve`): a typo fix, 2 round trips.

The payloads have the same shape as the proxy ones (request with
system/tools/messages + analysis, reconstructed SSE response) and include
`<system-reminder>` blocks to exercise the
[DetailPanel](/components/frontend.md) views.

# Examples

```bash
cd server
AGENTSPY_DB=./agentspy-demo.db uv run python ../scripts/seed_demo.py
AGENTSPY_DB=./agentspy-demo.db uv run agentspy
```
