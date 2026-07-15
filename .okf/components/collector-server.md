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
`https://api.anthropic.com`), `AGENTSPY_REHYDRATE_HOURS` (default 48 —
finestra di reidratazione del Correlator all'avvio, vedi
[correlazione](/design/correlation.md)), `AGENTSPY_PROVIDER` (default
`anthropic`) e `AGENTSPY_RUNTIME` (default `claude-code`) — vedi
[layer adapter](/design/adapter-layers.md).

# Moduli

| Modulo | Ruolo |
|--------|-------|
| `app.py` | Assemblaggio Starlette: `create_app(db_path, upstream)` per istanze isolate (test), `main()` legge env e lancia uvicorn. `_handle_round_trip()` collega proxy → correlate → store → WS. Serve `/ui/*` da `frontend/dist` con fallback SPA; catch-all → proxy. |
| `proxy.py` | `ProxyForwarder.forward()`: puro transport provider-agnostico — inoltro streaming, redazione header sensibili, timing, emissione record. Analisi body e ricostruzione SSE delegate al provider. |
| `providers/` | [Layer provider](/design/adapter-layers.md): `base.py` (`ProviderAdapter`, `StreamCollector`) + `anthropic.py` (`SSECollector`, `analyze_request_body`, normalizzazione usage). Registry con `get_provider()`. |
| `runtimes/` | [Layer agent runtime](/design/adapter-layers.md): `base.py` (`AgentRuntime`) + `claude_code.py` (vocabolario hook, header sessione, tool hint, slash-command) + `claude_code_artifacts.py` (ex `context_artifacts.py`). Registry con `get_runtime()`. |
| `correlate.py` | Assegna round trip a sessioni/turni/subagenti — la parte più delicata; il vocabolario Claude Code arriva dal runtime. Vedi [correlazione](/design/correlation.md). |
| `ingest.py` | `POST /ingest/hook` e `POST /ingest/mcp`. Vedi [ingest API](/interfaces/ingest-api.md). |
| `store.py` | SQLite WAL, connessione unica con lock, chiamate su thread; snippet/hint via runtime. Vedi [schema](/interfaces/sqlite-schema.md). |
| `api.py` | REST read-only. Vedi [REST API](/interfaces/rest-api.md). |
| `ws.py` | `ConnectionManager` per il broadcast. Vedi [WebSocket](/interfaces/websocket.md). |

Solo le vere chiamate al modello (`ProviderAdapter.is_model_call`: body con
`messages` + path che termina in `/messages`) vengono correlate e persistite
(scartati HEAD, `/v1/models`, `count_tokens`).

L'emissione del record verso `_handle_round_trip()` è best-effort e fuori dal
percorso critico: sul path non-streaming è fire-and-forget (`asyncio.create_task`),
sul ramo SSE è attesa ma protetta da try/except. Un errore di store (DB locked,
disco pieno) viene loggato e non trasforma un round trip riuscito in un 500.

# Dipendenze

`starlette>=0.37`, `uvicorn>=0.30`, `httpx>=0.27`, `websockets>=12`
(necessaria: senza, uvicorn rifiuta l'upgrade su `/ws` con 404).
Dev: `pytest`, `pytest-asyncio` (asyncio_mode=auto).

# Test

```bash
cd server && uv run pytest    # 40+ test: store, proxy, api, correlate
```
