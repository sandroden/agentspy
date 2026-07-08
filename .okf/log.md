# Bundle Update Log

## 2026-07-08
* **Update**: [frontend](/components/frontend.md) — rifiniture dashboard: click sui grafici apre il dettaglio in place, rimossi elenco sessioni e box quick start (quest'ultimo dietro il bottone "?" nel footer della sidebar), bolla Claude/LLM in timeline portata a verde (token `--c-llm`).
* **Creation**: [Riconoscimento di skill e slash-command](/design/skill-recognition.md) — badge 🎓 per il tool `Skill`, trigger di turno per gli slash-command e chip nel dettaglio che misura lo SKILL.md iniettato; aggiornato [frontend](/components/frontend.md) (`utils/command.ts`, icona Skill, SystemReminderText esteso).

## 2026-07-07
* **Update**: [Frontend](/components/frontend.md) — nomi delle due viste (Grafici = dashboard grafica, Timeline = flusso interazioni) e bottone della sidebar diventato toggle bidirezionale fra le due; documentato anche il badge coi round trip nella sidebar.
* **Initialization**: Creato il bundle OKF derivandolo da README.md, PLAN.md e dal codice sorgente.
* **Creation**: [Architettura](/architecture.md) con i tre canali di osservazione.
* **Creation**: Componenti — [collector server](/components/collector-server.md), [hook script](/components/hook-script.md), [wrapper MCP](/components/mcp-wrapper.md), [frontend](/components/frontend.md), [proxy standalone](/components/standalone-proxy.md), [seed demo](/components/seed-demo.md).
* **Creation**: Interfacce — [REST API](/interfaces/rest-api.md), [WebSocket](/interfaces/websocket.md), [ingest API](/interfaces/ingest-api.md), [schema SQLite](/interfaces/sqlite-schema.md), [formato JSONL](/interfaces/jsonl-log-format.md).
* **Creation**: Design — [correlazione](/design/correlation.md), [run tagging](/design/run-tagging.md), [token accounting](/design/token-accounting.md), [decisioni](/design/decisions.md).
* **Creation**: Runbook — [avvio rapido](/runbooks/quickstart.md), [sviluppo e test](/runbooks/development.md).
