---
type: Runbook
title: Quickstart
description: How to start the collector, route Claude Code through the proxy and open the UI.
tags: [runbook, getting-started]
timestamp: 2026-07-07T00:00:00Z
---

> User-facing install instructions live in
> [`docs/installation.md`](../../docs/installation.md); this runbook is the
> minimal internal cheat sheet.

# Steps

```bash
# 1. the collector (port 8082)
cd server && uv run agentspy

# 2. Claude Code through the proxy
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude

# 3. the UI
xdg-open http://127.0.0.1:8082/ui/
```

**Note**: if `ANTHROPIC_API_KEY` is in the environment it takes
precedence over the claude.ai login; in that case `env -u
ANTHROPIC_API_KEY ANTHROPIC_BASE_URL=... claude`.

# Optional channels

- **Hooks**: copy the `hooks` section of `hooks/settings-example.json`
  into the `.claude/settings.json` of the project to observe — see
  [hook script](/components/hook-script.md).
- **MCP**: replace the MCP server command with the
  [wrapper](/components/mcp-wrapper.md).
- **Run tags** to compare strategies — see
  [run tagging](/design/run-tagging.md).

# Trying the UI without real traffic

Use the [seed demo](/components/seed-demo.md):

```bash
cd server
AGENTSPY_DB=./agentspy-demo.db uv run python ../scripts/seed_demo.py
AGENTSPY_DB=./agentspy-demo.db uv run agentspy
```
