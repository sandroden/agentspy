---
type: Script
title: Seed demo (seed_demo.py)
description: Genera un DB dimostrativo per esplorare la UI senza traffico reale né consumo di token.
resource: scripts/seed_demo.py
tags: [demo, tooling]
timestamp: 2026-07-07T00:00:00Z
---

Importa `Store` e `analyze_request_body` da `agentspy_server`
(aggiunge `../server` a `sys.path`), cancella e ricrea il DB indicato da
`AGENTSPY_DB` (default `./agentspy-demo.db`) e lo popola con 3 sessioni:

- **A** (live, in evidenza, tag `demo-live`): 4 turni con prompt reali,
  2-3 round trip per turno, tool use vari, hook completi, un subagente
  `Explore` (sessione figlia, modello sonnet) e un evento MCP
  `context7:query-docs`.
- La sessione **figlia** del subagente.
- **B** (chiusa, corta, tag `demo-breve`): fix di un typo, 2 round trip.

I payload hanno la stessa forma di quelli del proxy (request con
system/tools/messages + analysis, response SSE ricostruita) e includono
blocchi `<system-reminder>` per esercitare le viste del
[DetailPanel](/components/frontend.md).

# Examples

```bash
cd server
AGENTSPY_DB=./agentspy-demo.db uv run python ../scripts/seed_demo.py
AGENTSPY_DB=./agentspy-demo.db uv run agentspy
```
