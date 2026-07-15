# Componenti

* [Collector server (agentspy_server)](collector-server.md) - Processo unico Starlette+uvicorn che assembla proxy, ingest, store SQLite, API REST/WS e UI statica sulla porta 8082.
* [Hook script (agentspy_hook.py)](hook-script.md) - Script hook fire-and-forget che inoltra i payload degli hook di Claude Code al collector; dà session_id reali e confini dei turni.
* [Wrapper MCP (agentspy_mcp_wrapper.py)](mcp-wrapper.md) - Relay stdio trasparente che spia il JSON-RPC fra Claude Code e un server MCP reale e lo inoltra al collector.
* [Frontend (Vue 3)](frontend.md) - UI interattiva per live e replay — dashboard, timeline verticale per turni, context-fill e pannello di dettaglio a tab.
* [Seed demo (seed_demo.py)](seed-demo.md) - Genera un DB dimostrativo per esplorare la UI senza traffico reale né consumo di token.
