# agentspy per opencode

Plugin per spiare il traffico di [opencode](https://opencode.ai) verso l'API
Anthropic con agentspy. Due canali, come per Claude Code:

- il **proxy** cattura i round trip HTTP (system prompt, tools, messaggi) —
  opencode ci punta impostando la `baseURL` del provider Anthropic;
- il **plugin** (`agentspy.js`) manda gli eventi nativi del runtime
  (`chat.message`, `tool.execute.before/after`, `session.idle`) all'ingest API,
  per la correlazione di sessioni e turni.

> Autenticazione: **solo API key a consumo** (`ANTHROPIC_API_KEY`). Questo
> plugin non usa e non richiede alcun bridge OAuth.

## 1. Server agentspy con runtime opencode

Avvia il server selezionando il runtime opencode (default sarebbe `claude-code`):

```bash
AGENTSPY_RUNTIME=opencode <comando di avvio del server agentspy>
```

Il runtime dichiara il vocabolario opencode (nomi hook nativi, nessun header di
sessione) usato dalla correlazione e dall'estrazione degli artefatti.

## 2. Configurazione opencode

opencode va configurato (in `opencode.json`, di progetto o globale) per:

1. inoltrare le richieste Anthropic al proxy agentspy;
2. caricare il plugin.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["/PERCORSO/ASSOLUTO/agentspy/hooks/opencode/agentspy.js"],
  "provider": {
    "anthropic": {
      "options": {
        "baseURL": "http://127.0.0.1:8082/v1"
      }
    }
  }
}
```

### Perché `/v1` nella baseURL

Il provider `@ai-sdk/anthropic` (quello che opencode usa sotto) ha come default
`https://api.anthropic.com/v1` e fa POST su `${baseURL}/messages`. opencode
passa la `baseURL` di config verbatim al factory `createAnthropic`, senza
aggiungere nulla. Quindi per colpire il proxy sul path che questo si aspetta
(`/v1/messages`, lo stesso di Anthropic) la `baseURL` **deve includere `/v1`**:
`http://127.0.0.1:8082/v1`. Ometterlo manderebbe le richieste su
`http://127.0.0.1:8082/messages`.

> Non affidarti alla variabile d'ambiente `ANTHROPIC_BASE_URL`: `@ai-sdk/anthropic`
> la legge verbatim e, se impostata senza `/v1`, dà 404. Meglio dichiarare
> `options.baseURL` esplicita in `opencode.json`.

In alternativa al campo `"plugin"` puoi lasciare il file in
`.opencode/plugin/agentspy.js` (nella root del progetto o in `~/.config/opencode/`):
opencode carica automaticamente i plugin da quella cartella.

## 3. Variabili d'ambiente del plugin

Lette dal plugin a runtime (lato opencode):

| Variabile | Default | Uso |
|-----------|---------|-----|
| `AGENTSPY_URL` | `http://127.0.0.1:8082` | base URL del server agentspy (l'ingest è `${AGENTSPY_URL}/ingest/hook`) |
| `AGENTSPY_TAG` | *(nessuno)* | tag opzionale per raggruppare/filtrare le sessioni |

## Limiti noti (mapping onesto)

Lo strumento è didattico: i dati riflettono la realtà del runtime, incluse le
zone d'ombra non ancora verificabili senza traffico reale.

- **Fine turno.** `session.idle` è mappato su `hook_stop`: come lo `Stop` di
  Claude Code scatta a fine di ogni risposta dell'assistente, non solo a fine
  sessione. La sessione torna "live" al `chat.message` o al tool successivo.
- **Correlazione della sessione principale — verificata (E2E 2026-07-16).**
  opencode non manda un header con l'id di sessione sulle richieste HTTP: il
  legame round trip ↔ sessione reale passa dal *prompt-binding* (testo
  dell'ultimo messaggio utente == `prompt` di un `chat.message`) e dal join per
  `tool_use_id`. In E2E la sessione risulta correttamente unica (`ses_…` con
  round trip, hook e turni coerenti). Resta il caso limite teorico di un
  `chat.message` che arrivi *dopo* il round trip (ingest lento/giù): lì si
  vedrebbe una sessione spezzata (round trip sotto `syn-<fingerprint>`).
- **`callID` == `toolu_…` — confermato (E2E 2026-07-16).** Il `callID` che
  opencode passa agli hook tool È l'id `toolu_…` della wire Anthropic: il join
  `tool_use_id → sessione` funziona come con Claude Code. Non ancora verificato
  invece il passaggio dell'id nel `_meta` delle tools/call **MCP**
  (`mcp_tool_use_id_key` resta vuoto finché non osservato).
- **Subagenti.** opencode esegue i subagenti come sessioni figlie (via il tool
  `task`, distinte da un `parentID`), senza hook di start/stop dedicati come
  Claude Code. La correlazione dei subagenti non è ancora implementata: gli
  eventi di un subagente restano al momento sulla sessione da cui è lanciato.
