---
type: Runbook
title: Avvio rapido
description: Come avviare il collector, instradare Claude Code attraverso il proxy e aprire la UI.
tags: [runbook, avvio]
timestamp: 2026-07-07T00:00:00Z
---

# Passi

```bash
# 1. il collector (porta 8082)
cd server && uv run agentspy

# 2. Claude Code attraverso il proxy
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude

# 3. la UI
xdg-open http://127.0.0.1:8082/ui/
```

**Nota**: se nell'ambiente c'è `ANTHROPIC_API_KEY` prende precedenza sul
login claude.ai; in tal caso `env -u ANTHROPIC_API_KEY
ANTHROPIC_BASE_URL=... claude`.

# Canali opzionali

- **Hooks**: copiare la sezione `hooks` di
  `hooks/settings-example.json` nel `.claude/settings.json` del progetto
  da osservare — vedi [hook script](/components/hook-script.md).
- **MCP**: sostituire il comando del server MCP col
  [wrapper](/components/mcp-wrapper.md).
- **Tag di run** per confrontare strategie — vedi
  [run tagging](/design/run-tagging.md).

# Provare la UI senza traffico reale

Usare il [seed demo](/components/seed-demo.md):

```bash
cd server
AGENTSPY_DB=./agentspy-demo.db uv run python ../scripts/seed_demo.py
AGENTSPY_DB=./agentspy-demo.db uv run agentspy
```
