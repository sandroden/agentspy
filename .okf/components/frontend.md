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
  token con selezione drag), `SubagentBars`.
- **SessionView**: `TimelineView` verticale raggruppata per turno
  (`TurnGroup`, `EventCard`, `HookMarker`, `McpCard`, `SubagentBlock`,
  `UsageBar`), `ContextFillPanel` (barra impilata per round trip),
  `TimeControls` (LIVE/PAUSA + scrubber, spazio e frecce).
- **DetailPanel** (colonna destra ridimensionabile): tab
  Sintesi | Richiesta | Risposta | Delta | JSON; sotto-componenti
  `ContentBlock`, `MessageBlock`, `JsonTree`, `SystemReminderText`
  (vista espansa/compatta dei `<system-reminder>`, persistita).
- **SessionsSidebar**: elenco ad albero con chip LIVE e badge unseen.

# Utility

- `utils/pricing.ts` — stima costo API per famiglia di modello (valori
  didattici in $/Mtoken; fable = fascia opus).
- `utils/model.ts` — famiglia/colore/abbreviazione del modello.
- `utils/toolIcon.ts` — emoji per tool (Read 📄, Edit ✏️, Bash 💻, …;
  `mcp__*` → 🔌).
- `utils/format.ts`, `composables/useElementSize.ts`.
