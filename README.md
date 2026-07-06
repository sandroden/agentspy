# agentspy

Strumento didattico per spiare la comunicazione fra Claude Code e l'API
Anthropic, mostrando come è composta ogni richiesta (system prompt, tools,
messages) e cosa risponde il modello (usage, cache, thinking, tool use).

## Componenti

* `agentspy_proxy.py` — proxy trasparente HTTP. Si mette fra Claude Code e
  `api.anthropic.com`, inoltra tutto tal quale (streaming SSE compreso) e
  registra ogni round trip.

## Uso

```bash
# terminale 1: avvia il proxy (default porta 8082)
./agentspy_proxy.py

# terminale 2: lancia Claude Code attraverso il proxy
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude
```

Nota: se nell'ambiente c'è una `ANTHROPIC_API_KEY` questa prende precedenza
sul login claude.ai; per usare l'abbonamento: `env -u ANTHROPIC_API_KEY ...`.

Output:

* **stdout** — una sintesi per ogni round trip in tempo reale:
  ```
  #007 00:41:12 POST /v1/messages claude-haiku-4-5 -> 200 in 2.4s (ttfb 1.3s)
       richiesta: system 30.2k ch, tools 11 (55k ch), messages 1 (16k ch)
       risposta:  input 10 | cache_write 26881 | output 103 | stop end_turn
  ```
* **`logs/run-<timestamp>.jsonl`** — un record JSON per round trip con:
  body completo della richiesta (system prompt integrale, definizioni tools,
  messages), risposta ricostruita dagli eventi SSE, usage dettagliato
  (input/output, cache read/write 5m/1h, thinking tokens), stop_reason,
  timing (ttfb, totale).

Variabili: `AGENTSPY_PORT`, `AGENTSPY_UPSTREAM`, `AGENTSPY_LOG_DIR`,
`AGENTSPY_SAVE_RAW=1` (salva anche gli eventi SSE grezzi).

## Stato

Prototipo validato end-to-end (2026-07-07) con una sessione reale
`claude -p` attraverso il proxy: cattura richieste parallele (round trip
principale + richieste di servizio), errori upstream inoltrati
trasparentemente, header di auth redatti nei log.

Prossimi passi previsti (vedi CLAUDE.md): collector con vista per turno
utente, gerarchia subagenti, wrapper MCP, frontend in tempo reale con
riempimento del contesto.
