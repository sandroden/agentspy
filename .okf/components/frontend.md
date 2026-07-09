---
type: Web App
title: Frontend (Vue 3)
description: UI interattiva per live e replay — dashboard, timeline verticale per turni, context-fill e pannello di dettaglio a tab.
resource: frontend/src
tags: [frontend, vue, vite, pinia, typescript]
timestamp: 2026-07-07T00:00:00Z
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

- **DashboardView** (`/ui/`): sessione "in evidenza" + card metriche
  (`MetricCards`, con stima costo da [token accounting](/design/token-accounting.md)),
  `ContextChart` (contesto per round trip), `CompositionChart` (area
  impilata cache_read/write/input/output), `CumulativeChart` (integrale
  token con selezione drag), `SubagentBars`. I pannelli-grafico rendono
  su **card scure** in entrambi i temi (i token di palette sono
  ridefiniti sul contenitore, così gli interni SVG — griglia, tick,
  testo, legende — si adattano). Il click su un punto di un grafico
  mette in evidenza quella sessione ma **non apre** il pannello di
  dettaglio: sulla dashboard il pannello destro è assente (gated sulla
  route, vive nella Timeline). L'elenco sessioni e il quick start non
  sono in dashboard: le sessioni stanno nella sidebar sinistra, il quick
  start dietro il bottone "?" in basso a sinistra.
- **SessionView**: `TimelineView` verticale raggruppata per turno
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
- **SessionsSidebar**: elenco ad albero; ogni riga mostra tag +
  eventuale titolo (lo UUID di sessione è omesso — il tag identifica) e,
  a destra, il badge col numero di round trip che ne codifica lo stato:
  vivido mentre la sessione gira, grigio quando è arrivato lo Stop
  (niente più chip LIVE). Più il badge unseen. In cima un bottone
  toggle fra le due viste — che hanno un nome: **Grafici** (la
  DashboardView su `/`) e **Timeline** (la SessionView). Sulla Timeline
  il bottone mostra "📊 Grafici"; sui Grafici mostra "🕒 Timeline" e
  torna all'ultima sessione aperta (`currentSessionId`, fallback
  `featuredSessionId`, disabilitato se entrambi nulli). In dashboard il
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
