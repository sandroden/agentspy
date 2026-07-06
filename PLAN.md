# agentspy — Piano di lavoro

Obiettivo: strumento didattico per spiare e **rappresentare in modo
interattivo e animato** la comunicazione fra Claude Code e l'API Anthropic
(più hooks e MCP), sia **dal vivo** sia in **replay** con cursore temporale.

Decisioni prese con Sandro (2026-07-07):

* Frontend: **Vue 3 + Vite puro** (Pinia, TS, rendering timeline custom).
* Storage: **SQLite** (payload completi + colonne indicizzate).
* Scope prima notte: nucleo + vista context-fill + hooks subagenti + wrapper MCP.
* Niente confronto side-by-side sincronizzato; però **ogni sessione ha un suo
  URL** (`/session/<id>`) così due sessioni si aprono in due pagine/tab.
* **Tag di raccolta** per separare run diverse: `ANTHROPIC_CUSTOM_HEADERS`
  con `x-agentspy-tag: <tag>` (attraversa il proxy) + env `AGENTSPY_TAG`
  letta dagli hooks. Il tag è filtrabile in UI.
* Multi-sessione: una alla volta in timeline, sidebar con elenco (badge live);
  subagenti annidati nella sessione madre, cliccabili per saltare alla loro
  vista; **totali aggregati** (token sessione + subagenti) in testata.
* Timeline **verticale** (il tempo scorre verso il basso); grafici classici
  (asse x = tempo) solo come vista opzionale.
* **Pausa del tempo**: modalità LIVE ↔ PAUSA, scrubber avanti/indietro su
  tutta la storia; i dati si raccolgono comunque, sempre.
* Click su qualunque evento → pannello di dettaglio con il payload completo.

## Architettura

Un **unico processo Python** (`server/`, Starlette + uvicorn, gestito con uv)
sulla porta 8082:

```
Claude Code --ANTHROPIC_BASE_URL--> [proxy /v1/*] --forward--> api.anthropic.com
hooks       --POST /ingest/hook -->  [collector]
wrapper MCP --POST /ingest/mcp  -->      |
                                     SQLite (agentspy.db)
                                         |
frontend  <--WS /ws (live)  +  REST /api/* (replay/dettaglio)
          <--statico /ui (build Vite)
```

Routing: `/api/*`, `/ws`, `/ingest/*`, `/ui/*` gestiti localmente;
**tutto il resto** inoltrato trasparente all'upstream (Claude Code chiama
anche `HEAD /` e altri path: mai rompere il forward).

### Componenti

1. `server/` — pacchetto Python (uv project):
   * `proxy.py` — evoluzione del prototipo `agentspy_proxy.py`: cattura
     round trip (richiesta completa + risposta ricostruita da SSE + usage +
     timing), li passa allo store e al broadcast WS.
   * `store.py` — SQLite (WAL). Scrittura sincrona semplice, payload JSON.
   * `correlate.py` — assegna i round trip a sessioni/turni/subagenti (vedi
     sotto). **La parte più delicata del backend.**
   * `api.py` — REST; `ws.py` — broadcast; `app.py` — assemblaggio + static.
2. `hooks/agentspy_hook.py` — script uv standalone: legge stdin (payload
   hook), POSTa a `/ingest/hook` con `AGENTSPY_TAG`; timeout 2s, exit 0
   sempre, zero dipendenze pesanti. + `hooks/settings-example.json`.
3. `mcp/agentspy_mcp_wrapper.py` — script uv: `wrapper.py -- <comando server
   mcp>`; relaya stdio nei due sensi, parsa i frame JSON-RPC (Content-Length
   o line-delimited), POSTa request/response accoppiate per `id`.
4. `frontend/` — Vite + Vue 3 + TS + Pinia + vue-router. Nessuna lib di
   chart per l'MVP (SVG/DOM custom).

### Schema SQLite

```sql
sessions(id TEXT PK,            -- session_id di Claude Code o sintetico
         tag TEXT, title TEXT, model TEXT,
         parent_session_id TEXT, agent_id TEXT,   -- per subagenti
         started_at REAL, ended_at REAL, live INTEGER)

events(id INTEGER PK,
       session_id TEXT, kind TEXT,     -- round_trip | hook | mcp
       subkind TEXT,                   -- hook_event_type / metodo JSON-RPC
       turn_index INTEGER, agent_id TEXT,
       ts_start REAL, ts_end REAL, ttfb_s REAL,
       model TEXT, status INTEGER, stop_reason TEXT,
       input_tokens INT, output_tokens INT,
       cache_read_tokens INT, cache_write_tokens INT,
       tool_names TEXT,                -- JSON array
       payload TEXT)                   -- JSON completo (request+response)
-- indici: (session_id, ts_start), (kind), (turn_index)
```

### Correlazione (correlate.py) — la parte difficile

Il traffico proxy non ha session_id; lo si ricava così, in ordine di forza:

1. **tool_use_id**: l'hook PreToolUse porta `session_id` + `tool_use_id`;
   il round trip precedente contiene il blocco `tool_use` con quell'id
   (`toolu_...`) → lega la conversazione API alla sessione hook.
2. **UserPromptSubmit**: il testo del prompt compare come ultimo messaggio
   user del round trip successivo → inizio turno (turn_index++).
3. **Fingerprint di conversazione**: hash di (system[0..N] + primo messaggio
   user); i round trip successivi della stessa conversazione estendono il
   prefisso dei messages → catena anche senza hooks.
4. **Header `x-agentspy-tag`** → assegna il tag.
5. **Subagenti**: SubagentStart/Stop (agent_id) + il `tool_use_id` della
   chiamata Agent + fingerprint diverso → sessione figlia con
   `parent_session_id`.

Senza hooks il sistema degrada bene: sessioni sintetiche da fingerprint,
turni euristici (ultimo messaggio user testuale ≠ tool_result).

### Contratto WS / REST

* `WS /ws` — server→client: `{type:'hello', sessions:[...]}`,
  `{type:'session', session:{...}}`, `{type:'event', event:<summary>}`.
* `GET /api/sessions` — elenco con aggregati (token totali **inclusi
  subagenti**, durata, n. turni, live, tag).
* `GET /api/sessions/:id/events` — summary ordinati (leggeri, senza payload).
* `GET /api/events/:id` — payload completo (caricato al click, lazy).
* `GET /api/sessions/:id/stats` — serie per context-fill.

Event summary: `{id, kind, subkind, session_id, turn_index, agent_id,
ts_start, duration_s, ttfb_s, model, status, stop_reason, usage{...},
tool_names, snippet}`.

## Frontend — specifica UI

Livelli di analisi (zoom progressivo):
* **L1 sessione**: turni compressi in righe con aggregati (round trip, token,
  durata) + testata con totali sessione+subagenti.
* **L2 turno**: espanso → i round trip del turno.
* **L3 round trip**: card con modello, timing (ttfb/totale), mini-barra
  usage (cache_read | cache_write | new | output), badge tool chiamati,
  indicatore thinking; hook come marker sottili; MCP come card proprie.
* **L4 dettaglio** (click su qualunque evento): pannello laterale a tab —
  Sintesi | Richiesta (system a blocchi, tools ripiegabili, messages) |
  Risposta (blocchi, thinking, tool_use input) | **Delta** (cosa è entrato
  nel contesto rispetto al round trip precedente) | JSON grezzo.

Componenti principali:
* `SessionsSidebar` — sessioni con badge live, tag, totali; click → route
  `/session/:id` (apribile in altra tab del browser).
* `TimelineView` — verticale, raggruppata per turno (header del prompt
  sticky); eventi nuovi entrano con animazione; toggle "segui" (autoscroll).
  Subagenti: blocco annidato/indentato con link "apri" → `/session/:childId`.
* `TimeControls` — LIVE/PAUSA, scrubber (slider) sull'indice degli eventi,
  step ±1, salto a inizio/fine. In pausa la timeline mostra solo eventi ≤
  cursore; lo stream continua a riempire lo store (nessun dato perso).
* `ContextFillPanel` — per round trip una barra orizzontale impilata:
  system / tools / storia / nuovo input (stimati in char→token ~/4) con
  overlay dei valori reali usage (cache_read/write/input/output); lista
  verticale allineata alla timeline + totale cumulativo. Grafico classico
  (tempo su x) rimandato come vista opzionale.
* Stato (Pinia): `sessions`, `events per sessione` (summary), `cursor`,
  `liveMode`, cache dei payload di dettaglio.

## Fasi ed esecuzione con subagenti

Politica modelli: **haiku** = scaffolding e compiti meccanici ben specificati;
**sonnet** = implementazione da specifica chiara; **fable (io)** = architettura,
correlate.py, integrazione, review finale, test E2E reali.

* **F1 — Specifiche** (io): questo documento + contratti sopra. ✅
* **F2 — Collector core** (sonnet, 1 agente): pacchetto `server/`,
  store, proxy integrato, ws, api, ingest; fixture di test = JSONL già
  catturato in `logs/`. Io: review + `correlate.py`.
* **F3 — Hooks + MCP wrapper** (in parallelo a F4):
  hook script (haiku, spec rigida); wrapper MCP (sonnet: stdio async delicato).
* **F4 — Frontend** (dopo il contratto F2, agenti sonnet in parallelo):
  scaffold Vite (haiku) → poi 3 filoni: (a) store Pinia + client WS/REST,
  (b) TimelineView + TimeControls, (c) DetailPanel + ContextFillPanel.
* **F5 — Integrazione ed E2E** (io): sessioni reali attraverso proxy+hooks
  (incluso un task con subagente e una chiamata MCP), verifica UI con
  screenshot via agent-browser, fix mirati.
* **F6 — Review e rifiniture**: passata /code-review, fix, README, commit.

Commit alla fine di ogni fase. Il DB e i log restano fuori dal repo.

## Rischi noti / decisioni rimandate

* Stima token per componente via char/4: approssimata; in futuro endpoint
  `count_tokens` per precisione.
* `ANTHROPIC_CUSTOM_HEADERS` da verificare empiricamente in F5.
* Richieste parallele/retry di Claude Code: ordinare per ts, tollerare
  out-of-order.
* Animazioni avanzate (flussi, transizioni elaborate): dopo l'MVP solido.
* Costi in €/$: non nell'MVP (i token bastano per il confronto didattico).
