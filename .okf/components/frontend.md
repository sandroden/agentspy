---
type: Web App
title: Frontend (Vue 3)
description: UI interattiva per live e replay — dashboard, timeline verticale per turni, context-fill e pannello di dettaglio a tab.
resource: frontend/src
tags: [frontend, vue, vite, pinia, typescript]
timestamp: 2026-07-10T00:00:00Z
---

Stack: **Vue 3 + Vite + TypeScript + Pinia + vue-router**, nessuna
libreria di chart (SVG/DOM custom). Base path `/ui/`; in dev il proxy
Vite inoltra `/api`, `/ingest`, `/ws` verso `127.0.0.1:8082`.

```bash
cd frontend && npm run dev      # hot reload
cd frontend && npm run build    # vue-tsc + vite build → dist/ servito su /ui
```

# Infrastruttura

- `api/client.ts` — fetch verso la [REST API](/interfaces/rest-api.md)
  (normalizza gli Usage, ricalcola lo snippet per il dettaglio) e
  `openStream()` sul [WebSocket](/interfaces/websocket.md) con
  riconnessione backoff 1s→10s.
- `stores/spy.ts` (Pinia) — stato centrale: sessioni, eventi per
  sessione, cursore/live (pausa del tempo), evento selezionato con cache
  dei dettagli, badge unseen. Getter `sessionTree` (albero madre/figli)
  e `visibleEvents` (filtrato da live/cursore).
- `router/index.ts` — `/` → DashboardView, `/session/:id` → SessionView
  (ogni sessione ha il suo URL, apribile in un'altra tab).
- `types.ts` — tipi speculari alle forme dello store Python.

# Viste e componenti

- **SessionHeader** (condiviso da Dashboard e Timeline): intestazione di
  sezione con nome della sessione (tag, fallback titolo/id), titolo
  secondario, pallino live, badge sub-agent, riga meta
  (modello · durata · token · round trip) e il toggle Timeline/Dashboard
  a destra. Stesso corpo/peso del brand **AgentSpy** nella sidebar
  (logo "A" + nome in `App.vue`, con pallino di stato WebSocket), così le
  due intestazioni si allineano. In dashboard sostituisce la vecchia
  barra identità: lo switch di sessione cambia l'header stesso.
- **MetricCards** (condiviso, `components/MetricCards.vue`): card
  metriche con icone emoji — peak context, token consumati (integrale),
  consumo/picco, prompt utente, round trip, sub-agent (🤖) e **stima
  costo** da [token accounting](/design/token-accounting.md), più il
  gruppo "+ sub-agents". Usato dalla dashboard e dalla Timeline
  (`SessionSummaryBar`, al posto del vecchio riepilogo
  input/output/cache), così i "numeri" si leggono uguali nelle due
  pagine; la card sub-agents è cliccabile solo in dashboard
  (prop `clickableSubagents`).
- **DashboardView** (`/ui/`): sessione "in evidenza" — `SessionHeader` +
  `MetricCards`,
  `ContextChart` (contesto per round trip), `CompositionChart` (area
  impilata cache_read/write/input/output), `CumulativeChart` (integrale
  token con selezione drag), `SubagentBars`. I pannelli-grafico rendono
  su **card scure** in entrambi i temi (i token di palette sono
  ridefiniti sul contenitore, così gli interni SVG — griglia, tick,
  testo, legende — si adattano). Il click su un punto di un grafico
  **porta alla Timeline** della sessione, in pausa su quell'esatto round
  trip e col dettaglio aperto (deep link `?event=<id>`, gestito da
  SessionView); sulla dashboard il pannello destro resta assente (gated
  sulla route, vive nella Timeline). L'elenco sessioni e il quick start non
  sono in dashboard: le sessioni stanno nella sidebar sinistra, il quick
  start dietro il bottone "?" in basso a sinistra.
- **SessionView**: `SessionHeader` (con i link parent/subagenti come
  slot), `TimelineView` verticale raggruppata per turno
  (`TurnGroup`, `EventCard`, `HookMarker`, `McpCard`, `SubagentBlock`,
  `UsageBar`), `ContextFillPanel` (barra impilata per round trip),
  `TimeControls` (LIVE/PAUSA + scrubber, spazio e frecce).
- **DetailPanel** (colonna destra ridimensionabile, presente solo nella
  Timeline): header con titolo "ROUND TRIP" + pill verde `#n/total` e riga
  meta monospace; tab Sintesi | Richiesta | Risposta | Delta | JSON — la
  Sintesi include un **donut** di distribuzione token
  (cache_read/write/input/output, con % da cache) a variabili di tema;
  sotto-componenti
  `ContentBlock`, `MessageBlock`, `JsonTree`, `SystemReminderText`
  (vista espansa/compatta dei `<system-reminder>` **e delle invocazioni
  di skill via slash-command**, persistita — vedi
  [skill & comandi](/design/skill-recognition.md)).
- **SessionsSidebar**: in cima il brand **AgentSpy** (in `App.vue`) e
  l'etichetta "Sessioni"; elenco ad albero; ogni riga mostra tag +
  eventuale titolo (lo UUID di sessione è omesso — il tag identifica) e,
  a destra, il badge col numero di round trip che ne codifica lo stato:
  vivido mentre la sessione gira, grigio quando è arrivato lo Stop
  (niente più chip LIVE). Più il badge unseen. Il toggle fra le due
  viste (`ViewToggle`, "🕐 Timeline | 📊 Dashboard") vive nel
  `SessionHeader` dell'area centrale: su "Timeline" torna all'ultima
  sessione aperta (`currentSessionId`, fallback `featuredSessionId`,
  disabilitato se entrambi nulli). In dashboard il
  click su una riga non naviga: mette la sessione in evidenza nei
  grafici. Nel footer i bottoni "?" (modal quick start) e ⚙️ Customize
  (tema light/dark).

I colori identità sono token CSS in `App.vue`, ridefiniti per tema
chiaro e scuro: `--c-user` blu, `--c-tool` ambra, `--c-llm` **verde**
per la bolla Claude/LLM in timeline, `--accent` per selezione/link.

# Utility

- `utils/pricing.ts` — stima costo API per famiglia di modello (valori
  didattici in $/Mtoken; fable = fascia opus).
- `utils/model.ts` — famiglia/colore/abbreviazione del modello.
- `utils/toolIcon.ts` — emoji per tool (Read 📄, Edit ✏️, Bash 💻, …;
  `Skill` → 🎓, `mcp__*` → 🔌).
- `utils/command.ts` — riconosce gli slash-command / skill nei messaggi
  user (vedi [skill & comandi](/design/skill-recognition.md)).
- `utils/format.ts`, `composables/useElementSize.ts`.
