# Development

```bash
cd server && uv run pytest          # collector tests (40+)
cd mcp && uv run --with pytest pytest tests/   # MCP wrapper tests
cd frontend && npm run dev          # UI with hot reload (proxy to 8082)
cd frontend && npm run build        # build served by the collector on /ui
```

The traffic ↔ sessions correlation (the delicate part) is in
`server/agentspy_server/correlate.py`, with the rules and limits documented in
the docstring. Real hook schema verified empirically (2026-07-07): the subagent
tool hooks carry `agent_id` but the parent's `session_id`.

## Trying the UI without real traffic

`scripts/seed_demo.py` generates a demo DB (a live session with tool use, a
subagent and an MCP event + a short closed session), useful to explore the
dashboard and panels without spending tokens:

```bash
cd server
AGENTSPY_DB=./agentspy-demo.db uv run python ../scripts/seed_demo.py
AGENTSPY_DB=./agentspy-demo.db uv run agentspy
```

Or with the justfile: `just seed` populates the demo DB and prints how to run
it.

## Known limitations / next steps

- Per-component token estimate (system/tools/messages) via characters/4; the
  real (exact) usage comes from the API response.
- The "classic" chart (time on the x-axis) is planned as an optional view, not
  yet implemented.
- Side-by-side comparison of two runs: for now two browser tabs.
- `PreCompact`/compaction: tracked as an event, the re-stitching of the
  compacted conversation to the same session is not yet handled.

## See also

- [Installation](installation.md) — the service commands (justfile).
- [UI guide](ui-guide.md) — what the frontend renders.
- [`.okf/index.md`](../.okf/index.md) — internal architecture and design
  knowledge.
- [`.okf/runbooks/development.md`](../.okf/runbooks/development.md) — internal
  development runbook.
