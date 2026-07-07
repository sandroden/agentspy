# agentspy

Strumento didattico per **spiare e visualizzare in tempo reale** la
comunicazione fra Claude Code e l'API Anthropic: come è composta ogni
richiesta (system prompt, tools, messages), cosa risponde il modello
(usage, cache, thinking, tool use), come lavorano subagenti e server MCP.

## Architettura

```
Claude Code --ANTHROPIC_BASE_URL--> [proxy /v1/*] --forward--> api.anthropic.com
hooks       --POST /ingest/hook -->  [collector]
wrapper MCP --POST /ingest/mcp  -->      |
                                     SQLite (agentspy.db)
                                         |
frontend  <--WS /ws (live)  +  REST /api/* (replay)  +  /ui (statico)
```

Un unico processo (`server/`, Starlette+uvicorn via uv) fa da proxy
trasparente, raccoglie tutto in SQLite e serve la UI. Tre canali di
osservazione, tutti opzionali e componibili:

1. **Proxy** (obbligatorio, il cuore): cattura ogni round trip completo —
   richiesta integrale e risposta ricostruita dallo stream SSE, con usage
   esatto (input/output, cache read/write 5m/1h, thinking) e timing.
2. **Hooks** (consigliato): dà session_id reali, confini dei turni
   (UserPromptSubmit) e ciclo di vita dei subagenti.
3. **Wrapper MCP** (per la didattica MCP): relay stdio trasparente che spia
   il JSON-RPC (initialize, tools/list, tools/call).

## Avvio rapido

```bash
# 1. il collector (porta 8082)
cd server && uv run agentspy

# 2. Claude Code attraverso il proxy
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude

# 3. la UI
xdg-open http://127.0.0.1:8082/ui/
```

Nota: se nell'ambiente c'è `ANTHROPIC_API_KEY` prende precedenza sul login
claude.ai: `env -u ANTHROPIC_API_KEY ANTHROPIC_BASE_URL=... claude`.

### Taggare le run (per confrontare strategie)

```bash
ANTHROPIC_CUSTOM_HEADERS='x-agentspy-tag: con-okf' \
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 AGENTSPY_TAG=con-okf claude
```

Il tag attraversa il proxy (header) e gli hooks (env) e in UI distingue le
raccolte; ogni sessione ha il suo URL (`/ui/session/<id>`), quindi due run
si aprono in due tab del browser.

### Hooks

Copia la sezione `hooks` di `hooks/settings-example.json` nel
`.claude/settings.json` del progetto da osservare, sostituendo
`/PATH/TO/agentspy`. Variabili: `AGENTSPY_URL`, `AGENTSPY_TAG`,
`AGENTSPY_DEBUG`. Lo script è fire-and-forget (exit 0 sempre, timeout 2s).

### Wrapper MCP

Nel config MCP sostituisci il comando del server con il wrapper:

```json
{"mcpServers": {"eco": {
  "command": "/path/agentspy/mcp/agentspy_mcp_wrapper.py",
  "args": ["--name", "eco", "--", "comando-server-reale", "arg1"]
}}}
```

Le `tools/call` vengono agganciate alla sessione giusta tramite il
`claudecode/toolUseId` che Claude Code passa nei `params._meta`.

## La UI

- **Timeline verticale** (il tempo scorre verso il basso), raggruppata per
  turno utente: card per i round trip (modello, timing, barra usage, badge
  tool, thinking), marker discreti per gli hook, card dedicate per le
  chiamate MCP, blocchi cliccabili per i subagenti (sessioni figlie con
  token aggregati nella madre).
- **Pausa del tempo**: LIVE/PAUSA + scrubber avanti/indietro su tutta la
  storia (spazio e frecce da tastiera); i dati si raccolgono comunque.
- **Click su qualsiasi evento** → pannello a tab: Sintesi | Richiesta
  (system prompt integrale a blocchi, tools, messages) | Risposta (thinking,
  testo, tool_use) | **Delta** (cosa è entrato nel contesto rispetto al giro
  precedente) | JSON grezzo.
- **Context-fill**: per ogni round trip una barra impilata cache_read /
  cache_write / nuovo / output — si vede il contesto riempirsi e quanto è
  servito dalla cache.

## Sviluppo

```bash
cd server && uv run pytest          # test collector (19)
cd mcp && uv run --with pytest pytest tests/   # test wrapper MCP
cd frontend && npm run dev          # UI con hot reload (proxy verso 8082)
cd frontend && npm run build        # build servita dal collector su /ui
```

La correlazione traffico↔sessioni (la parte delicata) è in
`server/agentspy_server/correlate.py`, con le regole e i limiti documentati
nel docstring. Schema hook reali verificati empiricamente (2026-07-07):
i tool hook dei subagenti portano `agent_id` ma il `session_id` della madre.

## Limiti noti / prossimi passi

- Stima token per componente (system/tools/messages) via caratteri/4;
  l'usage reale (esatto) arriva dalla risposta API.
- Il grafico "classico" (tempo sulle ascisse) è previsto come vista
  opzionale, non ancora implementato.
- Confronto affiancato di due run: per ora due tab del browser.
- `PreCompact`/compattazione: tracciata come evento, la ricucitura della
  conversazione compattata alla stessa sessione non è ancora gestita.
