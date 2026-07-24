# agentspy

An educational tool to **spy on and visualize in real time** the communication
between Claude Code and the Anthropic API: how each request is composed (system
prompt, tools, messages), what the model replies (usage, cache, thinking, tool
use), and how subagents and MCP servers work.

<img width="3430" height="1891" alt="immagine" src="https://github.com/user-attachments/assets/46759bdb-6752-4748-b662-3cbaa96fb59d" />

## Architecture

```
Claude Code --ANTHROPIC_BASE_URL--> [proxy /v1/*] --forward--> api.anthropic.com
hooks       --POST /ingest/hook -->  [collector]
wrapper MCP --POST /ingest/mcp  -->      |
                                     SQLite (agentspy.db)
                                         |
frontend  <--WS /ws (live)  +  REST /api/* (replay)  +  /ui (static)
```

A single process (`server/`, Starlette+uvicorn via uv) acts as a transparent
proxy, collects everything into SQLite and serves the UI. Three observation
channels, all optional and composable:

1. **Proxy** (mandatory, the core): captures every complete round trip — the
   full request and the response reconstructed from the SSE stream, with exact
   usage (input/output, cache read/write, thinking) and timing.
2. **Hooks** (recommended): provides real session_ids, turn boundaries
   (UserPromptSubmit) and the subagent life cycle.
3. **MCP wrapper** (for MCP teaching): a transparent stdio relay that spies on
   the JSON-RPC (initialize, tools/list, tools/call).

## Quick start

```bash
# 1. the collector (port 8082)
cd server && uv run agentspy

# 2. Claude Code through the proxy
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude

# 3. the UI
xdg-open http://127.0.0.1:8082/ui/
```

Note: if `ANTHROPIC_API_KEY` is present in the environment it takes precedence
over the claude.ai login: `env -u ANTHROPIC_API_KEY ANTHROPIC_BASE_URL=...
claude`.

For the one-command setup (`install.sh` + the `claude-spy` shell function), see
[docs/installation.md](docs/installation.md).

## Documentation

- [installation.md](docs/installation.md) — install scripts, the `claude-spy`
  shell function, justfile service commands.
- [providers-and-gateways.md](docs/providers-and-gateways.md) — routing one
  instance per upstream: Anthropic and GLM via OpenRouter, the ToS note.
- [opencode.md](docs/opencode.md) — spying on opencode: runtime, plugin,
  `baseURL` setup, known limits.
- [hooks.md](docs/hooks.md) — the hooks channel: setup, what each hook carries,
  degraded mode.
- [mcp-wrapper.md](docs/mcp-wrapper.md) — the transparent MCP stdio relay.
- [run-tagging.md](docs/run-tagging.md) — tagging runs to compare strategies.
- [ui-guide.md](docs/ui-guide.md) — dashboard, timeline, detail panel, cleaning
  up sessions.
- [development.md](docs/development.md) — tests, build, demo seed, known
  limitations.

Internal architecture and design knowledge live in [.okf/](.okf/index.md).

## Development

```bash
cd server && uv run pytest          # collector tests
cd frontend && npm run build        # UI build, served by the collector on /ui
```

More in [docs/development.md](docs/development.md).
