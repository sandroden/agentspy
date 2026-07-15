---
type: Component
title: Plugin opencode (hooks/opencode)
description: Plugin JS per opencode che traduce gli eventi nativi del runtime nel formato neutro dell'ingest API; controparte dello hook script di Claude Code.
resource: hooks/opencode
tags: [opencode, plugin, hooks, ingest]
timestamp: 2026-07-16T00:00:00Z
---

Controparte per opencode dello [hook script](/components/hook-script.md) di
Claude Code: `agentspy.js` è un plugin ESM che opencode carica in-process
(via campo `plugin` di `opencode.json` o da `.opencode/plugin/`) e che POSTa
gli eventi a `POST /ingest/hook` — fire-and-forget, timeout 500ms, mai
propagare errori all'agente.

Traduce gli eventi nativi nel formato neutro dell'ingest
([confine del layer runtime](/design/adapter-layers.md)): gli
`hook_event_name` restano i nomi NATIVI di opencode (`chat.message`,
`tool.execute.before/after`, `session.idle`), dichiarati nel vocabolario di
`OpencodeRuntime` (`server/agentspy_server/runtimes/opencode.py`).

Fatti verificati in E2E (2026-07-16, opencode 1.18):

- il `callID` degli hook tool **è** il `toolu_…` della wire Anthropic → il
  join `tool_use_id → sessione` funziona come con Claude Code;
- la correlazione produce una sessione unica `ses_…` (prompt-binding +
  join), senza header di sessione HTTP;
- opencode inietta le istruzioni nel **system prompt** come blocco unico
  concatenato con marcatori `Instructions from: <path>` (AGENTS.md **e**
  `~/.claude/CLAUDE.md`), seguiti dalle sezioni skills/mcp/references:
  l'estrattore (`runtimes/opencode_artifacts.py`) scorpora per span fino
  all'incipit di sezione nota;
- config: `provider.anthropic.options.baseURL` deve includere `/v1`.

Limiti correnti in `hooks/opencode/README.md` (subagenti via `parentID` non
correlati, `_meta` MCP non osservato). Auth: solo API key a consumo (i token
OAuth Pro/Max in tool terzi violano i ToS Anthropic 2026).

# Citations

[1] `hooks/opencode/README.md` — installazione e limiti.
[2] `hooks/opencode/agentspy.js` — implementazione.
