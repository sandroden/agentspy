---
type: Component
title: MCP wrapper (agentspy_mcp_wrapper.py)
description: Transparent stdio relay that spies on the JSON-RPC between Claude Code and a real MCP server and forwards it to the collector.
resource: mcp/agentspy_mcp_wrapper.py
tags: [mcp, json-rpc, python]
timestamp: 2026-07-07T00:00:00Z
---

Launches the real MCP server command (after `--`) as a subprocess and
relays the stdio both ways **line by line, byte-identical** (MCP stdio is
line-delimited JSON-RPC). Separate threads for stdin→child, child
stdout→parent, stderr passthrough and an `http_worker` with an async
queue.

**The relay has absolute priority**: if the spy or the endpoint fail, the
line passes through anyway with no delay. It handles SIGTERM/SIGINT by
terminating the child, drains the queue at process end (2s) and exits
with the child's returncode. Payload truncation at 200,000 characters.

The `Spy` class classifies each line (request / notification / response)
and pairs request↔response by `id`, then POSTs to
`AGENTSPY_URL/ingest/mcp` (2s timeout) — see
[ingest API](/interfaces/ingest-api.md).

# Configuration

In the MCP config you replace the server command with the wrapper:

```json
{"mcpServers": {"eco": {
  "command": "/path/agentspy/mcp/agentspy_mcp_wrapper.py",
  "args": ["--name", "eco", "--", "real-server-command", "arg1"]
}}}
```

Arguments: `--name NAME` (default: basename of the command), `--url URL`
(default: env `AGENTSPY_URL`). Env: `AGENTSPY_URL`, `AGENTSPY_TAG`,
`AGENTSPY_DEBUG`.

# Binding to the session

`tools/call` are bound to the right session through
`params._meta["claudecode/toolUseId"]`, which Claude Code passes in the
call → `Correlator.session_for_tool_use` (see
[correlation](/design/correlation.md)). Lifecycle events (initialize,
tools/list) remain without a session.

# Tests

```bash
cd mcp && uv run --with pytest pytest tests/   # with fake_mcp_server.py
```
