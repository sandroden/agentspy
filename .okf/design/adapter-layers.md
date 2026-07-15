---
type: Design
title: Layer adapter — provider e agent runtime
description: Due assi di specializzazione (providers/ per il protocollo LLM, runtimes/ per le convenzioni del coding agent) dietro cui è confinata tutta la conoscenza Anthropic/Claude Code del backend.
tags: [design, estensibilità, provider, runtime]
timestamp: 2026-07-16T00:00:00Z
---

L'accoppiamento del backend a "Claude Code che parla con Anthropic" vive su
due assi indipendenti, ciascuno confinato in un package specializzabile con
registry + variabile d'ambiente:

| Layer | Package | Isola | Selezione |
|-------|---------|-------|-----------|
| Provider | `server/agentspy_server/providers/` | protocollo wire dell'API LLM: cos'è una chiamata al modello, analisi del body, ricostruzione dallo stream SSE, nomi dei campi usage | `AGENTSPY_PROVIDER` (default `anthropic`) |
| Agent runtime | `server/agentspy_server/runtimes/` | convenzioni del coding agent: header di sessione, nomi hook, ponte MCP, ultimo messaggio utente reale, hint dei tool, snippet slash-command, artefatti del contesto | `AGENTSPY_RUNTIME` (default `claude-code`) |

Supportare **opencode con modelli Anthropic** = nuovo `AgentRuntime`;
supportare **codex/OpenAI** = nuovo `ProviderAdapter` (parser Responses API)
+ nuovo `AgentRuntime`.

# Il modello neutro è la forma Anthropic

Decisione chiave: il modello interno persistito e renderizzato — blocchi
content `text|thinking|tool_use|tool_result|image`, usage con nomi neutri
(`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`)
nelle colonne DB — è deliberatamente **derivato dalla Messages API di
Anthropic**. Conseguenze:

- per Anthropic la traduzione è ~identità → i DB già catturati restano
  validi senza migrazione;
- il frontend (che dispatcha su `block.type` e legge le colonne usage) non
  cambia: un provider nuovo *traduce* il suo wire format in questo modello
  al momento dell'ingest, dentro `StreamCollector.finalize()` e
  `normalize_usage()`;
- il body grezzo della richiesta resta persistito com'è passato sul filo:
  è il materiale didattico, non viene normalizzato via.

# Interfacce

`ProviderAdapter` (providers/base.py): `is_model_call(path, body)`,
`analyze_request(body)`, `stream_collector()`, `json_response_summary(body)`,
`normalize_usage(usage)`. Il `ProxyForwarder` resta puro transport
provider-agnostico; il record emesso porta il campo `provider`.

`AgentRuntime` (runtimes/base.py): vocabolario dichiarativo
(`session_id_header`, `hook_user_prompt`, `hook_pre/post_tool_use`,
`hook_subagent_start/stop`, `hook_stop`, `mcp_tool_use_id_key`,
`system_reminder_prefix`) + helper derivati (`is_session_end`,
`is_subagent_hook`, `is_tool_call_hook`, `tool_use_id_from_mcp_meta`,
`is_system_reminder`) + parser astratti (`last_user_message`, `tool_hint`,
`command_snippet`, `extract_artifacts`). L'inventario artefatti di Claude
Code (ex `context_artifacts.py`) è ora `runtimes/claude_code_artifacts.py`,
dettaglio implementativo di `ClaudeCodeRuntime`.

# Confini del layer runtime

- I **nomi dei campi del payload hook** (`session_id`, `prompt`,
  `tool_use_id`, `tool_name`, `agent_id`…) NON passano dal runtime: sono il
  formato neutro dell'[ingest API](/interfaces/ingest-api.md). Per un agente
  i cui eventi nativi hanno altra forma, la traduzione è compito dello
  script hook/plugin lato agente, non del server.
- Le euristiche *generiche* di [correlazione](/design/correlation.md)
  (fingerprint sha256, sessioni sintetiche, turn detection strutturale)
  restano nel `Correlator`; dal runtime prende solo il vocabolario.
- Il **frontend** non è (ancora) parametrizzato: famiglie modello, finestre
  di contesto, pricing, icone tool restano tabelle claude-centriche in
  `frontend/src/utils/` — estendibili, ma fuori da questi layer.

# Citations

[1] `server/agentspy_server/providers/base.py` — contratto e razionale del modello neutro.
[2] `server/agentspy_server/runtimes/base.py` — contratto e confini del layer runtime.
