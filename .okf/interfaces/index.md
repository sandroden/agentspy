# Interfaces

* [REST API (/api/*)](rest-api.md) - Read-only REST endpoints used by the frontend for replay and lazy detail.
* [WebSocket (/ws)](websocket.md) - Live server→client channel for sessions and events; the client reconnects with backoff.
* [Ingest API (/ingest/*)](ingest-api.md) - Ingestion endpoints for Claude Code hook events and the MCP wrapper.
* [SQLite schema (agentspy.db)](sqlite-schema.md) - Two tables — sessions and events — with full JSON payloads and indexed columns for the timeline.
* [JSONL format of the standalone proxy logs](jsonl-log-format.md) - One JSON record per line for each round trip, captured back then by the standalone prototype (now removed); the files in logs/ remain as test fixtures.
