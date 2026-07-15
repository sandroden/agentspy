---
type: Architecture
title: Architettura di agentspy
description: Processo unico Starlette che fa da proxy trasparente, collector e server UI, con tre canali di osservazione componibili.
tags: [architettura, proxy, collector]
timestamp: 2026-07-07T00:00:00Z
---

agentspy è uno strumento didattico per spiare e visualizzare in tempo
reale la comunicazione fra Claude Code e l'API Anthropic. L'intero
backend è **un unico processo Python** (Starlette + uvicorn, gestito con
uv) sulla porta **8082**, implementato dal
[collector server](/components/collector-server.md).

```
Claude Code --ANTHROPIC_BASE_URL--> [proxy /v1/*] --forward--> api.anthropic.com
hooks       --POST /ingest/hook -->  [collector]
wrapper MCP --POST /ingest/mcp  -->      |
                                     SQLite (agentspy.db)
                                         |
frontend  <--WS /ws (live)  +  REST /api/* (replay)  +  /ui (statico)
```

Routing: `/api/*`, `/ws`, `/ingest/*`, `/ui/*` gestiti localmente;
**tutto il resto** inoltrato trasparente all'upstream (Claude Code chiama
anche `HEAD /` e altri path: il forward non va mai rotto).

La conoscenza specifica di Anthropic (protocollo wire) e di Claude Code
(hook, header, artefatti) è confinata in due layer specializzabili —
`providers/` e `runtimes/` — descritti in
[layer adapter](/design/adapter-layers.md).

# Canali di osservazione

Tre canali, tutti componibili; solo il primo è obbligatorio:

1. **Proxy** (il cuore): cattura ogni round trip completo — richiesta
   integrale e risposta ricostruita dallo stream SSE, con usage esatto
   (input/output, cache read/write 5m/1h, thinking) e timing.
2. **Hooks** ([hook script](/components/hook-script.md), consigliato):
   dà session_id reali, confini dei turni (UserPromptSubmit) e ciclo di
   vita dei subagenti.
3. **Wrapper MCP** ([mcp wrapper](/components/mcp-wrapper.md), per la
   didattica MCP): relay stdio trasparente che spia il JSON-RPC.

I tre flussi convergono nella [correlazione](/design/correlation.md),
che assegna il traffico a sessioni/turni/subagenti, e finiscono nello
[schema SQLite](/interfaces/sqlite-schema.md). Il
[frontend](/components/frontend.md) legge via
[REST](/interfaces/rest-api.md) (replay) e
[WebSocket](/interfaces/websocket.md) (live).

# Unità concettuali

- **Round trip**: una richiesta/risposta verso `/v1/messages`; l'unità
  della timeline.
- **Turno**: gruppo di round trip aperto da un prompt utente
  (UserPromptSubmit o euristica).
- **Sessione**: conversazione Claude Code; i subagenti sono sessioni
  figlie (`parent_session_id`) con token aggregati nella madre.

# Citations

[1] `README.md` del repository — panoramica e avvio rapido.
[2] `PLAN.md` del repository — piano di lavoro e decisioni.
