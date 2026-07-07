---
okf_version: "0.1"
---

# agentspy — Knowledge Bundle

Strumento didattico per spiare e visualizzare in tempo reale la
comunicazione fra Claude Code e l'API Anthropic.

# Panoramica

* [Architettura di agentspy](architecture.md) - Processo unico Starlette che fa da proxy trasparente, collector e server UI, con tre canali di osservazione componibili.

# Sezioni

* [Componenti](components/) - Collector server, hook script, wrapper MCP, frontend Vue, proxy standalone legacy, seed demo.
* [Interfacce](interfaces/) - REST API, WebSocket, ingest API, schema SQLite, formato JSONL.
* [Design](design/) - Correlazione traffico↔sessioni, tag di raccolta, contabilità token/costi, decisioni architetturali.
* [Runbook](runbooks/) - Avvio rapido e sviluppo/test.
