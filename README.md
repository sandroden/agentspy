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

### Provare la UI senza traffico reale

`scripts/seed_demo.py` genera un DB dimostrativo (sessione live con tool
use, subagente ed evento MCP + una sessione breve chiusa), utile per
esplorare dashboard e pannelli senza consumare token:

```bash
cd server
AGENTSPY_DB=./agentspy-demo.db uv run python ../scripts/seed_demo.py
AGENTSPY_DB=./agentspy-demo.db uv run agentspy
```

### Taggare le run (per confrontare strategie)

```bash
ANTHROPIC_CUSTOM_HEADERS='x-agentspy-tag: con-okf' \
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 AGENTSPY_TAG=con-okf claude
```

Le due variabili portano lo **stesso tag su due canali diversi**, e
convergono sullo stesso campo `tag` della sessione:

- `ANTHROPIC_CUSTOM_HEADERS` viaggia col traffico API: Claude Code aggiunge
  l'header `x-agentspy-tag` a ogni richiesta e il proxy lo applica alla
  sessione a cui attribuisce il round trip;
- `AGENTSPY_TAG` viaggia con gli hook: lo script la legge dall'ambiente e
  la manda a `/ingest/hook` (arriva anche alle sessioni figlie dei
  subagenti).

A regime ne basta una, purché il suo canale sia attivo: senza hook
installati serve l'header; con il proxy in mezzo (sempre, quando si spia)
l'header da solo è sufficiente. Impostarle entrambe è ridondanza a costo
zero che copre i casi limite: l'header tagga anche processi che ereditano
l'ambiente ma non hanno hook (es. un `claude -p` lanciato da
un'automazione), la env tagga anche eventi hook di traffico non ancora
attribuito dal correlatore.

In UI il tag distingue le raccolte; ogni sessione ha il suo URL
(`/ui/session/<id>`), quindi due run si aprono in due tab del browser.

### Hooks

Copia la sezione `hooks` di `hooks/settings-example.json` nel
`.claude/settings.json` del progetto da osservare, sostituendo
`/PATH/TO/agentspy`. Variabili: `AGENTSPY_URL`, `AGENTSPY_TAG`,
`AGENTSPY_DEBUG`. Lo script è fire-and-forget (exit 0 sempre, timeout 2s):
legge il payload JSON che Claude Code gli passa su stdin e lo inoltra tal
quale a `/ingest/hook`, senza mai bloccare o rallentare la sessione.

**Agganciare gli hook "al volo"** (senza toccare il settings del progetto):
i settings di Claude Code non hanno un meccanismo di include, ma il flag
`--settings` carica un file (o JSON inline) per la singola invocazione, con
priorità massima e merge sugli altri livelli. `settings-example.json` è già
un file settings completo, quindi — dopo averne fatto una copia con il path
reale al posto di `/PATH/TO/agentspy` — basta:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 \
claude --settings /path/reale/agentspy/hooks/settings-example.json
```

In alternativa, per osservare *tutti* i progetti senza ripeterlo a ogni
invocazione, la stessa sezione `hooks` può stare nei settings utente
globali `~/.claude/settings.json` (gli hook lì valgono ovunque; il
collector spento non disturba, lo script hook fallisce in silenzio).

**Ruolo globale.** Il proxy vede *tutto il contenuto* (richieste e risposte
integrali) ma non sa *di chi* è quel traffico: le richieste HTTP non
portano session_id, non distinguono un nuovo prompt utente dalla
continuazione automatica di un loop di tool, e non dicono se una
conversazione è un subagente. Gli hook sono il canale "anagrafico" che
fornisce questa struttura; il correlatore
(`server/agentspy_server/correlate.py`) usa i due flussi insieme: senza
hook le sessioni restano sintetiche (`syn-<fingerprint>`) con turni
euristici, con gli hook diventano sessioni reali con confini di turno
esatti.

Cosa porta ciascun hook:

| Hook | Informazione | Uso in agentspy |
|---|---|---|
| `SessionStart` / `SessionEnd` | `session_id` reale, cwd, transcript_path | nasce/termina la sessione in UI, stato LIVE |
| `UserPromptSubmit` | il prompt dell'utente, `session_id` | avanza il turno in modo autoritativo (raggruppamento della timeline); "binding via prompt": aggancia al session_id reale le conversazioni senza tool call; marker ▶ verde col testo del prompt; conteggio/marker prompt della dashboard |
| `PreToolUse` / `PostToolUse` | `tool_name`, `tool_use_id`, input/output del tool | la regola di correlazione più forte: il `tool_use_id` compare anche nel round trip catturato dal proxy e lega la conversazione API alla sessione hook; marker 🔧 col nome del tool |
| `SubagentStart` / `SubagentStop` | `agent_id`, tipo di agente | crea la sessione figlia (`sub-<agent_id>`) con `parent_session_id`, da cui: blocchi subagente nella timeline, barre subagenti e token "incl. subagenti" in dashboard |
| `Stop` | fine del giro di risposte | marker ■ di chiusura turno |
| `PreCompact`, `Notification` | compattazione, notifiche | per ora solo tracciati come eventi (la ricucitura post-compattazione non è ancora gestita) |

Ogni evento hook porta inoltre il tag (`AGENTSPY_TAG`) e un timestamp, e
resta visibile in timeline come marker cliccabile col suo payload JSON
integrale nel pannello di dettaglio.

**Senza hook funziona comunque**, in modalità degradata: il fingerprint di
conversazione (sha256 di system + primo messaggio user) incatena i round
trip della stessa conversazione, e il nuovo turno viene inferito dal testo
dell'ultimo messaggio user. Ma i session_id sono sintetici, i subagenti non
vengono riconosciuti come figli e i confini di turno sono euristici: per
l'uso didattico pieno (seguire un subagente, contare i round trip di un
prompt) gli hook sono di fatto necessari.

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

### Dashboard (home)

Il punto d'ingresso (`/ui/`) è una dashboard di sintesi. Una **sessione in
evidenza** (di default quella live, o la più recente; selezionabile dal
menu in alto a destra) guida card e grafici:

- **Card metriche**: contesto di picco, token totali consumati
  ("integrale"), rapporto consumo/picco, prompt utente, round trip,
  subagenti coi loro token, stima del costo API (pricing per famiglia di
  modello, solo dati reali — nessuna proiezione ipotetica).
- **Contesto per round trip**: una linea per sessione (l'evidenziata in
  blu, le altre attenuate), marker verdi sui round trip aperti da un prompt
  utente, linea rossa del tetto ~200k quando la scala lo giustifica.
- **Di cosa è fatto il contesto**: area impilata cache_read / cache_write /
  input nuovo / output.
- **Consumo cumulativo**: l'integrale dei token; **trascinando col mouse**
  si seleziona un intervallo e si leggono token e costo di quel tratto.
- **Subagenti**: barre orizzontali (colore = modello) con i token di ogni
  sessione figlia.

Ogni punto dei grafici è **cliccabile**: porta alla sessione con l'evento
corrispondente già selezionato. In fondo, la lista delle sessioni e la
guida di avvio rapido.

### Timeline di sessione

- **Timeline verticale** (il tempo scorre verso il basso), raggruppata per
  turno utente: card per i round trip (modello, timing, barra usage, badge
  tool con icona — 📄 Read, ✏️ Edit, 💻 Bash, 🔍 Grep… — e thinking),
  marker per gli hook (▶ verde con lo snippet del prompt per
  UserPromptSubmit, 🔧 col nome del tool per Pre/PostToolUse), card viola
  per le chiamate MCP, card arancio cliccabili per i subagenti (sessioni
  figlie, token aggregati nella madre). Ogni riga ha un indicatore
  colorato per tipo; la legenda è in fondo alla timeline.
- Nella sidebar la **sessione live** è evidenziata (chip LIVE, bordo verde).
- **Pausa del tempo**: LIVE/PAUSA + scrubber avanti/indietro su tutta la
  storia (spazio e frecce da tastiera); i dati si raccolgono comunque.
- **Context-fill**: per ogni round trip una barra impilata cache_read /
  cache_write / nuovo / output — si vede il contesto riempirsi e quanto è
  servito dalla cache.

### Pannello di dettaglio (colonna destra)

Click su qualsiasi evento → pannello a tab: Sintesi | Richiesta (system
prompt integrale a blocchi, tools, messages) | Risposta (thinking, testo,
tool_use) | **Delta** (cosa è entrato nel contesto rispetto al giro
precedente) | JSON grezzo.

- La colonna è **ridimensionabile** trascinando il bordo sinistro (la
  larghezza viene ricordata).
- I blocchi `<system-reminder>` che Claude Code inserisce accanto al prompt
  utente hanno due viste, commutabili con la checkbox **"vista compatta"**
  nell'header: espansa (reminder evidenziati in violetto, distinti dal
  prompt reale) o compatta (reminder ridotti a chip "⚙ system-reminder ·
  N char"; click sul chip → popup col contenuto integrale).

Terminologia: l'unità della timeline è il *round trip* (una
richiesta/risposta verso `/v1/messages`); il pannello ne mostra il
*payload*; dentro `messages[]` ogni messaggio è fatto di *content block*
(`text`, `tool_use`, `tool_result`).

### Pulizia delle sessioni

Il pulsante **🗑 Modifica** in testa alla sidebar attiva la modalità
selezione: ogni sessione mostra una checkbox e, selezionando una madre, le
figlie (subagenti) risultano spuntate e bloccate perché verranno eliminate
in cascata. La barra in fondo (**Elimina N sessioni** / **Annulla**) chiede
conferma e rimuove sessioni ed eventi in modo definitivo; se elimini la
sessione aperta la UI torna alla dashboard.

Da riga di comando:

```bash
# elimina una sessione (con le sue discendenti)
curl -X DELETE http://127.0.0.1:8082/api/sessions/<id>

# elimina più sessioni in un colpo
curl -X POST http://127.0.0.1:8082/api/sessions/delete \
     -H 'Content-Type: application/json' -d '{"ids": ["id1", "id2"]}'
```

Entrambe rispondono `{"deleted": [...]}` con l'elenco completo degli id
rimossi (incluse le figlie). L'eliminazione è **in cascata** sulle sessioni
figlie e **definitiva**.

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
