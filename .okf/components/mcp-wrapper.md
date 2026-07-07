---
type: Component
title: Wrapper MCP (agentspy_mcp_wrapper.py)
description: Relay stdio trasparente che spia il JSON-RPC fra Claude Code e un server MCP reale e lo inoltra al collector.
resource: mcp/agentspy_mcp_wrapper.py
tags: [mcp, json-rpc, python]
timestamp: 2026-07-07T00:00:00Z
---

Lancia il comando del server MCP reale (dopo `--`) come sottoprocesso e
relaya lo stdio nei due sensi **riga per riga, byte identici** (MCP
stdio è JSON-RPC line-delimited). Thread separati per stdin→figlio,
stdout figlio→padre, stderr passthrough e un `http_worker` con coda
asincrona.

**Il relay ha priorità assoluta**: se lo spione o l'endpoint falliscono,
la riga passa comunque senza ritardi. Gestisce SIGTERM/SIGINT terminando
il figlio, drena la coda a fine processo (2s) ed esce col returncode del
figlio. Troncamento payload a 200.000 caratteri.

La classe `Spy` classifica ogni riga (request / notification / response)
e accoppia request↔response per `id`, poi POSTa a
`AGENTSPY_URL/ingest/mcp` (timeout 2s) — vedi
[ingest API](/interfaces/ingest-api.md).

# Configurazione

Nel config MCP si sostituisce il comando del server col wrapper:

```json
{"mcpServers": {"eco": {
  "command": "/path/agentspy/mcp/agentspy_mcp_wrapper.py",
  "args": ["--name", "eco", "--", "comando-server-reale", "arg1"]
}}}
```

Argomenti: `--name NAME` (default: basename del comando), `--url URL`
(default: env `AGENTSPY_URL`). Env: `AGENTSPY_URL`, `AGENTSPY_TAG`,
`AGENTSPY_DEBUG`.

# Aggancio alla sessione

Le `tools/call` vengono legate alla sessione giusta tramite
`params._meta["claudecode/toolUseId"]` che Claude Code passa nella
chiamata → `Correlator.session_for_tool_use` (vedi
[correlazione](/design/correlation.md)). Gli eventi di lifecycle
(initialize, tools/list) restano senza sessione.

# Test

```bash
cd mcp && uv run --with pytest pytest tests/   # con fake_mcp_server.py
```
