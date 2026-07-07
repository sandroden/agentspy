# Interfacce

* [REST API (/api/*)](rest-api.md) - Endpoint REST read-only usati dal frontend per replay e dettaglio lazy.
* [WebSocket (/ws)](websocket.md) - Canale live server→client per sessioni ed eventi; il client riconnette con backoff.
* [Ingest API (/ingest/*)](ingest-api.md) - Endpoint di ingestione per gli eventi degli hook di Claude Code e del wrapper MCP.
* [Schema SQLite (agentspy.db)](sqlite-schema.md) - Due tabelle — sessions ed events — con payload JSON completi e colonne indicizzate per la timeline.
* [Formato JSONL dei log del proxy standalone](jsonl-log-format.md) - Un record JSON per riga per ogni round trip catturato dal prototipo agentspy_proxy.py; usato come fixture nei test.
