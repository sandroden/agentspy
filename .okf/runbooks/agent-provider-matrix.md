---
type: Runbook
title: Matrice agente × provider — tutte le varianti di setup
description: Come instradare le combinazioni Claude Code/opencode × Anthropic/GLM-via-OpenRouter attraverso agentspy, cosa cambia in ciascuna e cosa serve per aggiungerne di nuove.
tags: [runbook, provider, runtime, openrouter, opencode, glm]
timestamp: 2026-07-16T00:00:00Z
---

La regola che governa tutto (vedi [layer adapter](/design/adapter-layers.md)):

- il **ProviderAdapter** dipende dal *wire format* dell'endpoint, non dal
  modello. Finché il traffico parla la Messages API di Anthropic — anche
  attraverso un gateway compatibile come OpenRouter — il provider è
  `anthropic`, qualunque modello ci giri sopra (GLM incluso);
- l'**AgentRuntime** dipende da *chi genera il traffico* (Claude Code,
  opencode…), non da dove va.

Ogni istanza di agentspy ha **un** upstream: per osservare due upstream in
parallelo (es. Anthropic e OpenRouter) si lanciano due istanze con porta e
DB dedicati, e si punta ciascun agente (base URL + `AGENTSPY_URL` per gli
hook) alla sua istanza.

# Matrice

| Variante | Provider | Runtime | Upstream | Auth | Stato |
|----------|----------|---------|----------|------|-------|
| Claude Code + Anthropic | `anthropic` | `claude-code` | `api.anthropic.com` (default) | abbonamento o `ANTHROPIC_API_KEY` | in uso |
| Claude Code + GLM via OpenRouter | `anthropic` | `claude-code` | `https://openrouter.ai/api` | `ANTHROPIC_AUTH_TOKEN=$OPENROUTER_API_KEY` | validata E2E 2026-07-16 |
| opencode + Anthropic | `anthropic` | `opencode` | `api.anthropic.com` (default) | `ANTHROPIC_API_KEY` a consumo (vedi nota ToS) | validata E2E 2026-07-16 |
| opencode + GLM via OpenRouter | `anthropic` | `opencode` | `https://openrouter.ai/api` | `OPENROUTER_API_KEY` | da validare (combinazione delle due sopra) |
| codex / client OpenAI-format | da scrivere | da scrivere | — | — | prospettiva |

**Nota ToS (2026)**: gli abbonamenti Claude Pro/Max funzionano SOLO dentro
Claude Code — i token OAuth in tool terzi sono vietati dai ToS Anthropic
(aggiornamento 2026-02-19) e bloccati server-side. Con opencode l'unica via
legittima verso modelli Claude è la API key a consumo. I bridge/workaround
(es. plugin che impersonano Claude Code) espongono l'account a sospensione.

# 1. Claude Code + Anthropic (setup standard)

Vedi [avvio rapido](/runbooks/quickstart.md): istanza default su 8082,
`ANTHROPIC_BASE_URL=http://127.0.0.1:8082`.

# 2. Claude Code + GLM via OpenRouter

OpenRouter espone un endpoint Anthropic-compatibile (`/api/v1/messages`):
Claude Code ci parla nativamente, quindi runtime e provider restano quelli
di default. Cambia solo l'upstream dell'istanza:

```bash
cd server && AGENTSPY_PORT=8083 AGENTSPY_UPSTREAM=https://openrouter.ai/api \
  AGENTSPY_DB=agentspy-openrouter.db uv run agentspy
```

Funzione di lancio (variante spy della `oclaude` di Sandro):

```bash
oclaude-spy () {
  ( export ANTHROPIC_BASE_URL="http://127.0.0.1:8083"
    export ANTHROPIC_API_KEY=""
    export ANTHROPIC_AUTH_TOKEN="$OPENROUTER_API_KEY"
    export ANTHROPIC_MODEL="z-ai/glm-5.2"
    export ANTHROPIC_SMALL_FAST_MODEL="z-ai/glm-4.7-flash"
    export AGENTSPY_URL="http://127.0.0.1:8083"
    export ANTHROPIC_CUSTOM_HEADERS="x-agentspy-tag: glm"   # tag sul traffico proxy
    claude )
}
```

Tutto il resto funziona invariato: gli hook sono quelli di Claude Code,
`x-claude-code-session-id` viaggia comunque (lo manda la CLI), l'header
`Authorization` con la chiave OpenRouter viene redatto prima della
persistenza. Il frontend riconosce la famiglia `glm` (colore blu, finestra
200k per 4.x / 1M per 5.x, tariffe OpenRouter in `pricing.ts`).

Particolarità dell'emulazione OpenRouter osservate in E2E (2026-07-16):

- `message_start` arriva con usage a **zero** e i token veri stanno in
  `message_delta`: il collector li accetta dal delta solo in questo caso
  (se `message_start` li riporta, restano congelati — vedi
  [token accounting](/design/token-accounting.md));
- `message_delta.usage` porta anche il **costo reale** in dollari
  (`cost`, `cost_details`): è persistito nel payload, non ancora usato
  dalla UI (che stima da tariffe per famiglia).

# 3. opencode + Anthropic

Serve il runtime `opencode` (`AGENTSPY_RUNTIME=opencode` sull'istanza) e il
plugin di ingest lato opencode: vedi `hooks/opencode/README.md` per
l'installazione (plugin + `provider.anthropic.options.baseURL` puntato
all'istanza agentspy). Auth: solo API key a consumo.

# 4. opencode + GLM via OpenRouter

Stessa idea della variante 2 (l'istanza punta a OpenRouter) + runtime
`opencode` come nella 3. Il punto delicato: il provider `openrouter`
*nativo* di opencode parla il formato OpenAI, che agentspy non sa ancora
interpretare. Bisogna invece dichiarare in `opencode.json` un provider
custom in **formato Anthropic** (SDK `@ai-sdk/anthropic`) puntato
all'istanza agentspy, con i modelli GLM:

```jsonc
{
  "provider": {
    "glm-spy": {
      "npm": "@ai-sdk/anthropic",
      "options": {
        "baseURL": "http://127.0.0.1:8083/v1",
        "apiKey": "{env:OPENROUTER_API_KEY}"
      },
      "models": { "z-ai/glm-5.2": {}, "z-ai/glm-4.7-flash": {} }
    }
  }
}
```

Così il wire format resta Messages API lungo tutta la catena
(opencode → agentspy → OpenRouter) e il provider `anthropic` di agentspy
continua a funzionare. *Da validare in E2E: sintassi provider custom e
passaggio dell'apiKey come header corretto.*

# 5. codex / client in formato OpenAI (prospettiva)

Qui cambia il wire format: serve un nuovo `ProviderAdapter` (parser dello
stream della Responses/Chat Completions API, normalizzazione di blocchi e
usage nel modello neutro) più un `AgentRuntime` per il client. È il lavoro
"grande" descritto in [layer adapter](/design/adapter-layers.md); nessuna
delle varianti sopra lo richiede.
