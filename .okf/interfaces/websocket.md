---
type: API
title: WebSocket (/ws)
description: Canale live server→client per sessioni ed eventi; il client riconnette con backoff.
resource: server/agentspy_server/ws.py
tags: [api, websocket, live]
timestamp: 2026-07-07T00:00:00Z
---

Canale **solo server→client** gestito da `ConnectionManager` nel
[collector server](/components/collector-server.md). Richiede la
dipendenza `websockets` (senza, uvicorn rifiuta l'upgrade con 404).

# Messaggi

| Messaggio | Quando |
|-----------|--------|
| `{type:'hello', sessions:[...]}` | all'apertura della connessione |
| `{type:'event', event:<summary>}` | nuovo evento (round trip, hook, MCP) |
| `{type:'session', session:{...}}` | sessione creata/aggiornata |
| `{type:'session_removed', id}` | sessione sintetica assorbita da una reale (merge in [correlazione](/design/correlation.md)) |

L'event summary è lo stesso della [REST API](/interfaces/rest-api.md).
I messaggi in ingresso servono solo a rilevare la disconnessione; la
riconnessione con backoff 1s→10s è nel client
(`frontend/src/api/client.ts`, vedi [frontend](/components/frontend.md)).
