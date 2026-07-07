---
type: Service
title: Collector server (agentspy_server)
description: Processo unico Starlette+uvicorn che assembla proxy, ingest, store SQLite, API REST/WS e UI statica sulla porta 8082.
resource: server/agentspy_server
tags: [backend, python, starlette, uv]
timestamp: 2026-07-07T00:00:00Z
---

Pacchetto Python `agentspy_server` (uv project, hatchling, Python ≥3.11).
Entry point: `agentspy = "agentspy_server.app:main"`. È il cuore
dell'[architettura](/architecture.md).

# Avvio

```bash
cd server && uv run agentspy     # ascolta 127.0.0.1:8082
```

Variabili d'ambiente: `AGENTSPY_PORT` (default 8082), `AGENTSPY_DB`
(default `./agentspy.db`), `AGENTSPY_UPSTREAM` (default
`https://api.anthropic.com`).

# Moduli

| Modulo | Ruolo |
|--------|-------|
| `app.py` | Assemblaggio Starlette: `create_app(db_path, upstream)` per istanze isolate (test), `main()` legge env e lancia uvicorn. `_handle_round_trip()` collega proxy → correlate → store → WS. Serve `/ui/*` da `frontend/dist` con fallback SPA; catch-all → proxy. |
| `proxy.py` | `ProxyForwarder.forward()`: inoltro streaming con `SSECollector` che ricostruisce il messaggio assistant, usage, ttfb. `analyze_request_body()` scompone system/tools/messages in conteggi caratteri. Redige header sensibili. Evoluzione del [prototipo standalone](/components/standalone-proxy.md). |
| `correlate.py` | Assegna round trip a sessioni/turni/subagenti — la parte più delicata. Vedi [correlazione](/design/correlation.md). |
| `ingest.py` | `POST /ingest/hook` e `POST /ingest/mcp`. Vedi [ingest API](/interfaces/ingest-api.md). |
| `store.py` | SQLite WAL, connessione unica con lock, chiamate su thread. Vedi [schema](/interfaces/sqlite-schema.md). |
| `api.py` | REST read-only. Vedi [REST API](/interfaces/rest-api.md). |
| `ws.py` | `ConnectionManager` per il broadcast. Vedi [WebSocket](/interfaces/websocket.md). |

Solo le richieste il cui body contiene `messages` vengono correlate e
persistite (scartati HEAD, `/v1/models`, `count_tokens`).

# Dipendenze

`starlette>=0.37`, `uvicorn>=0.30`, `httpx>=0.27`, `websockets>=12`
(necessaria: senza, uvicorn rifiuta l'upgrade su `/ws` con 404).
Dev: `pytest`, `pytest-asyncio` (asyncio_mode=auto).

# Test

```bash
cd server && uv run pytest    # 19 test: store, proxy, api, correlate
```
