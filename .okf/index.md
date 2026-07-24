---
okf_version: "0.1"
---

# agentspy — Knowledge Bundle

Educational tool to spy on and visualize, in real time, the
communication between Claude Code and the Anthropic API.

# Overview

* [agentspy architecture](architecture.md) - Single Starlette process acting as transparent proxy, collector and UI server, with three composable observation channels.

# Sections

* [Components](components/) - Collector server, hook script, MCP wrapper, Vue frontend, legacy standalone proxy, seed demo.
* [Interfaces](interfaces/) - REST API, WebSocket, ingest API, SQLite schema, JSONL format.
* [Design](design/) - Traffic↔session correlation, collection tags, token/cost accounting, architectural decisions.
* [Runbooks](runbooks/) - Quickstart and development/testing.
