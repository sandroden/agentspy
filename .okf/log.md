# Bundle Update Log

## 2026-07-17
* **Creation**: [Plugin opencode](/components/opencode-plugin.md) — secondo `AgentRuntime` (`runtimes/opencode.py` + `opencode_artifacts.py` + plugin JS), validato E2E: correlazione a sessione unica, `callID` == `toolu_…`, artefatti scorporati dal system a blocco unico. Aggiornato [layer adapter](/design/adapter-layers.md).
* **Creation**: [Matrice agente × provider](/runbooks/agent-provider-matrix.md) — le varianti Claude Code/opencode × Anthropic/GLM-via-OpenRouter, con stato di validazione e particolarità dell'emulazione OpenRouter (usage nel delta, campo `cost`).
* **Update**: [Token accounting](/design/token-accounting.md) e [frontend](/components/frontend.md) — famiglia `glm` (colore, finestra 200k/1M, tariffe OpenRouter); collector: usage di prompt accettato da `message_delta` solo se `message_start` non ne riporta.

## 2026-07-16
* **Creation**: [Layer adapter — provider e agent runtime](/design/adapter-layers.md) — la conoscenza Anthropic/Claude Code del backend confinata nei package specializzabili `providers/` e `runtimes/`; modello neutro persistito = forma Anthropic. Aggiornati [architettura](/architecture.md), [collector server](/components/collector-server.md), [correlazione](/design/correlation.md), [skill recognition](/design/skill-recognition.md).
* **Deletion**: Proxy standalone (`agentspy_proxy.py` e relativo concept) — prototipo rimosso dal repo; il [formato JSONL](/interfaces/jsonl-log-format.md) resta documentato come storico (i log in `logs/` servono ancora da fixture nei test).

## 2026-07-08
* **Update**: [frontend](/components/frontend.md) — rifiniture dashboard: click sui grafici apre il dettaglio in place, rimossi elenco sessioni e box quick start (quest'ultimo dietro il bottone "?" nel footer della sidebar), bolla Claude/LLM in timeline portata a verde (token `--c-llm`).
* **Creation**: [Riconoscimento di skill e slash-command](/design/skill-recognition.md) — badge 🎓 per il tool `Skill`, trigger di turno per gli slash-command e chip nel dettaglio che misura lo SKILL.md iniettato; aggiornato [frontend](/components/frontend.md) (`utils/command.ts`, icona Skill, SystemReminderText esteso).

## 2026-07-07
* **Update**: [Frontend](/components/frontend.md) — nomi delle due viste (Grafici = dashboard grafica, Timeline = flusso interazioni) e bottone della sidebar diventato toggle bidirezionale fra le due; documentato anche il badge coi round trip nella sidebar.
* **Initialization**: Creato il bundle OKF derivandolo da README.md, PLAN.md e dal codice sorgente.
* **Creation**: [Architettura](/architecture.md) con i tre canali di osservazione.
* **Creation**: Componenti — [collector server](/components/collector-server.md), [hook script](/components/hook-script.md), [wrapper MCP](/components/mcp-wrapper.md), [frontend](/components/frontend.md), proxy standalone (rimosso il 2026-07-16), [seed demo](/components/seed-demo.md).
* **Creation**: Interfacce — [REST API](/interfaces/rest-api.md), [WebSocket](/interfaces/websocket.md), [ingest API](/interfaces/ingest-api.md), [schema SQLite](/interfaces/sqlite-schema.md), [formato JSONL](/interfaces/jsonl-log-format.md).
* **Creation**: Design — [correlazione](/design/correlation.md), [run tagging](/design/run-tagging.md), [token accounting](/design/token-accounting.md), [decisioni](/design/decisions.md).
* **Creation**: Runbook — [avvio rapido](/runbooks/quickstart.md), [sviluppo e test](/runbooks/development.md).
