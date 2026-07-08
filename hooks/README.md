# AgentSpy Hook

Hook per Claude Code che invia telemetria degli eventi di sessione a un server AgentSpy.

## Uso

Copia la sezione `hooks` da `settings-example.json` nel tuo `.claude/settings.json` e sostituisci il placeholder `/PATH/TO/agentspy` con il percorso assoluto della directory agentspy.

In alternativa, `install.sh` (Linux/macOS) o `install.ps1` (Windows) nella
root del repo automatizzano questo passaggio e aggiungono una funzione
shell `claude-spy [tag]` che usa direttamente il file generato — vedi il
paragrafo "Install" del README principale.

Esempio:
```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "/home/username/agentspy/hooks/agentspy_hook.py"}]}],
    ...
  }
}
```

## Comportamento

Lo script:
1. Legge lo stdin in formato JSON
2. Costruisce un payload con timestamp, tag e i dati ricevuti
3. Invia un POST JSON all'endpoint `/ingest/hook` del server AgentSpy
4. Ignora silenziosamente qualsiasi errore (timeout, connessione, eccezioni)
5. Esce sempre con status 0

## Variabili d'ambiente

- `AGENTSPY_URL`: URL base del server (default: `http://127.0.0.1:8082`)
- `AGENTSPY_TAG`: Tag identificativo per la sessione (opzionale)
- `AGENTSPY_DEBUG`: Se impostato a `1`, stampa gli errori su stderr

Esempio:
```bash
export AGENTSPY_URL=http://localhost:8082
export AGENTSPY_TAG=my-session
export AGENTSPY_DEBUG=1
```
