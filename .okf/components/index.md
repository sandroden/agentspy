# Components

* [Collector server (agentspy_server)](collector-server.md) - Single Starlette+uvicorn process assembling proxy, ingest, SQLite store, REST/WS API and static UI on port 8082.
* [Hook script (agentspy_hook.py)](hook-script.md) - Fire-and-forget hook script that forwards Claude Code hook payloads to the collector; provides real session_ids and turn boundaries.
* [opencode plugin (hooks/opencode)](opencode-plugin.md) - JS plugin for opencode that translates the runtime's native events into the neutral ingest API format; counterpart of the Claude Code hook script.
* [MCP wrapper (agentspy_mcp_wrapper.py)](mcp-wrapper.md) - Transparent stdio relay that spies on the JSON-RPC between Claude Code and a real MCP server and forwards it to the collector.
* [Frontend (Vue 3)](frontend.md) - Interactive UI for live and replay — dashboard, vertical timeline by turn, context-fill and a tabbed detail panel.
* [Seed demo (seed_demo.py)](seed-demo.md) - Generates a demo DB to explore the UI without real traffic or token consumption.
