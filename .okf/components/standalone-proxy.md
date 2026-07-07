---
type: Prototype
title: Proxy standalone (agentspy_proxy.py)
description: Prototipo originale self-contained — solo proxy trasparente con log JSONL su file, senza SQLite né UI; precursore di server/proxy.py.
resource: agentspy_proxy.py
tags: [proxy, prototipo, legacy, uv-script]
timestamp: 2026-07-07T00:00:00Z
---

Script uv single-file (`#!/usr/bin/env -S uv run --script`, dependencies
inline: starlette, uvicorn, httpx). Proxy trasparente verso
`api.anthropic.com`: riassume ogni round trip su stdout e lo salva
integralmente in un file [JSONL](/interfaces/jsonl-log-format.md) sotto
`logs/`.

**Non fa parte della catena runtime del server**: niente SQLite, UI,
correlazione o WS. `server/agentspy_server/proxy.py` (vedi
[collector server](/components/collector-server.md)) ne è l'evoluzione:
stessa logica di forward e ricostruzione SSE, ma parametrizzata e con
callback `on_event` al posto della scrittura su file.

```bash
./agentspy_proxy.py                                  # 127.0.0.1:8082
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude
```

# Variabili d'ambiente

| Variabile | Default | Uso |
|-----------|---------|-----|
| `AGENTSPY_PORT` | 8082 | porta di ascolto |
| `AGENTSPY_UPSTREAM` | `https://api.anthropic.com` | upstream |
| `AGENTSPY_LOG_DIR` | `./logs` | directory dei JSONL |
| `AGENTSPY_SAVE_RAW` | — | `1` = salva anche gli eventi SSE grezzi |

# Differenze rispetto al proxy integrato

- Scrive su `logs/run-<ts>.jsonl` invece di passare a correlate/store.
- Supporta `AGENTSPY_SAVE_RAW` e il `content_summary` nel `finalize()`.
- Route catch-all senza HEAD/OPTIONS (il server integrato li gestisce).

I JSONL catturati da questo prototipo sono usati come fixture dai test
del collector.
