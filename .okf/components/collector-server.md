---
type: Service
title: Collector server (agentspy_server)
description: Single Starlette+uvicorn process assembling proxy, ingest, SQLite store, REST/WS API and static UI on port 8082.
resource: server/agentspy_server
tags: [backend, python, starlette, uv]
timestamp: 2026-07-07T00:00:00Z
---

Python package `agentspy_server` (uv project, hatchling, Python ≥3.11).
Entry point: `agentspy = "agentspy_server.app:main"`. It is the core of
the [architecture](/architecture.md).

# Startup

```bash
cd server && uv run agentspy     # listens on 127.0.0.1:8082
```

Environment variables: `AGENTSPY_PORT` (default 8082), `AGENTSPY_DB`
(default `./agentspy.db`), `AGENTSPY_UPSTREAM` (default
`https://api.anthropic.com`), `AGENTSPY_REHYDRATE_HOURS` (default 48 —
the Correlator's rehydration window at startup, see
[correlation](/design/correlation.md)), `AGENTSPY_PROVIDER` (default
`anthropic`) and `AGENTSPY_RUNTIME` (default `claude-code`) — see
[adapter layers](/design/adapter-layers.md).

# Modules

| Module | Role |
|--------|------|
| `app.py` | Starlette assembly: `create_app(db_path, upstream)` for isolated instances (tests), `main()` reads env and launches uvicorn. `_handle_round_trip()` connects proxy → correlate → store → WS. Serves `/ui/*` from `frontend/dist` with SPA fallback; catch-all → proxy. |
| `proxy.py` | `ProxyForwarder.forward()`: pure provider-agnostic transport — streaming forward, redaction of sensitive headers, timing, record emission. Body analysis and SSE reconstruction delegated to the provider. |
| `providers/` | [Provider layer](/design/adapter-layers.md): `base.py` (`ProviderAdapter`, `StreamCollector`) + `anthropic.py` (`SSECollector`, `analyze_request_body`, usage normalization). Registry via `get_provider()`. |
| `runtimes/` | [Agent runtime layer](/design/adapter-layers.md): `base.py` (`AgentRuntime`) + `claude_code.py` (hook vocabulary, session header, tool hints, slash-commands) + `claude_code_artifacts.py` (formerly `context_artifacts.py`). Registry via `get_runtime()`. |
| `correlate.py` | Assigns round trips to sessions/turns/subagents — the most delicate part; the Claude Code vocabulary comes from the runtime. See [correlation](/design/correlation.md). |
| `ingest.py` | `POST /ingest/hook` and `POST /ingest/mcp`. See [ingest API](/interfaces/ingest-api.md). |
| `store.py` | SQLite WAL, single locked connection, calls dispatched to threads; snippet/hint via runtime. See [schema](/interfaces/sqlite-schema.md). |
| `api.py` | Read-only REST. See [REST API](/interfaces/rest-api.md). |
| `ws.py` | `ConnectionManager` for broadcast. See [WebSocket](/interfaces/websocket.md). |

Only true model calls (`ProviderAdapter.is_model_call`: body with
`messages` + path ending in `/messages`) are correlated and persisted
(HEAD, `/v1/models`, `count_tokens` are discarded).

Record emission toward `_handle_round_trip()` is best-effort and off the
critical path: on the non-streaming path it is fire-and-forget
(`asyncio.create_task`), on the SSE branch it is awaited but guarded by
try/except. A store error (DB locked, disk full) is logged and does not
turn a successful round trip into a 500.

# Dependencies

`starlette>=0.37`, `uvicorn>=0.30`, `httpx>=0.27`, `websockets>=12`
(required: without it, uvicorn rejects the `/ws` upgrade with a 404).
Dev: `pytest`, `pytest-asyncio` (asyncio_mode=auto).

# Tests

```bash
cd server && uv run pytest    # 40+ tests: store, proxy, api, correlate
```
