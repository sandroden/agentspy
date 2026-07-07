---
type: Runbook
title: Sviluppo e test
description: Comandi per test del backend, test del wrapper MCP e sviluppo/build del frontend.
tags: [runbook, sviluppo, test]
timestamp: 2026-07-07T00:00:00Z
---

# Comandi

```bash
cd server && uv run pytest                       # test collector (19)
cd mcp && uv run --with pytest pytest tests/     # test wrapper MCP
cd frontend && npm run dev                       # UI hot reload (proxy → 8082)
cd frontend && npm run build                     # build servita dal collector su /ui
```

# Punti d'attenzione

- La parte delicata è la [correlazione](/design/correlation.md)
  (`server/agentspy_server/correlate.py`): regole e limiti sono
  documentati nel docstring del modulo.
- I test del collector usano come fixture i
  [JSONL](/interfaces/jsonl-log-format.md) già catturati in `logs/`.
- Lo schema reale degli hook è stato verificato empiricamente
  (2026-07-07): i tool hook dei subagenti portano `agent_id` ma il
  `session_id` della madre.
- Il DB (`agentspy.db`) e i log restano fuori dal repository.
- Il frontend in dev gira su Vite con proxy verso `127.0.0.1:8082`; in
  produzione il [collector](/components/collector-server.md) serve
  `frontend/dist` su `/ui` (404 esplicito se non compilato).
