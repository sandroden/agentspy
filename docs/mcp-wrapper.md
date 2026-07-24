# MCP wrapper

The MCP wrapper is the third observation channel, for teaching how MCP works.
It is a transparent stdio relay that spies on the JSON-RPC exchange
(`initialize`, `tools/list`, `tools/call`) between Claude Code and an MCP
server.

## Setup

In the MCP config, replace the server command with the wrapper:

```json
{"mcpServers": {"eco": {
  "command": "/path/agentspy/mcp/agentspy_mcp_wrapper.py",
  "args": ["--name", "eco", "--", "real-server-command", "arg1"]
}}}
```

The wrapper relays stdio in both directions and forwards each request/response
pair to `/ingest/mcp`.

## Correlation

The `tools/call` are attached to the right session via the
`claudecode/toolUseId` that Claude Code passes in `params._meta`.

## See also

- [Hooks](hooks.md) — the hooks channel that provides session structure.
- [UI guide](ui-guide.md) — MCP calls appear as purple cards in the timeline.
- [`.okf/components/mcp-wrapper.md`](../.okf/components/mcp-wrapper.md) —
  internal notes on the wrapper.
