---
type: Component
title: Hook script (agentspy_hook.py)
description: Script hook fire-and-forget che inoltra i payload degli hook di Claude Code al collector; dà session_id reali e confini dei turni.
resource: hooks/agentspy_hook.py
tags: [hooks, claude-code, python]
timestamp: 2026-07-07T00:00:00Z
---

Script Python stdlib puro (solo `urllib`, zero dipendenze pesanti).
Legge lo stdin (payload hook JSON, fallback `{"raw": <testo troncato>}`),
costruisce `{ts, tag, payload}` e fa POST a `AGENTSPY_URL/ingest/hook`
(vedi [ingest API](/interfaces/ingest-api.md)) con timeout **0.5s**
(sincrono nel ciclo hook: un collector lento non deve stallare l'agente).

**Fire-and-forget**: ignora qualsiasi eccezione ed esce sempre con
exit 0, per non bloccare mai Claude Code. Debug su stderr solo con
`AGENTSPY_DEBUG=1`.

# Hook intercettati

`hooks/settings-example.json` (da copiare in `.claude/settings.json` del
progetto osservato, sostituendo `/PATH/TO/agentspy`) registra 10 hook:

`SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreToolUse` (`*`),
`PostToolUse` (`*`), `SubagentStart`, `SubagentStop`, `Stop`,
`PreCompact`, `Notification`.

Il backend usa dal payload: `hook_event_name`, `session_id`,
`agent_id`/`agent_type`, `tool_use_id`, `tool_name`, `prompt`.

# Variabili d'ambiente

| Variabile | Default | Uso |
|-----------|---------|-----|
| `AGENTSPY_URL` | `http://127.0.0.1:8082` | endpoint del collector |
| `AGENTSPY_TAG` | — | tag di raccolta, vedi [run tagging](/design/run-tagging.md) |
| `AGENTSPY_DEBUG` | — | `1` = log su stderr |

# Ruolo nella correlazione

È il canale che dà alla [correlazione](/design/correlation.md) i
session_id reali, i confini di turno (UserPromptSubmit) e il ciclo di
vita dei subagenti. Nota empirica (2026-07-07): i tool hook generati
dentro un subagente portano `agent_id` ma il `session_id` della madre.
