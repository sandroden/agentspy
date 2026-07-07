---
type: Decision Record
title: Decisioni architetturali (2026-07-07)
description: Decisioni prese con Sandro all'avvio del progetto — stack, storage, UX della timeline — e cose esplicitamente rimandate.
tags: [decisioni, architettura]
timestamp: 2026-07-07T00:00:00Z
---

Decisioni prese con Sandro il 2026-07-07 (fonte: PLAN.md):

- **Frontend**: Vue 3 + Vite puro (Pinia, TS, rendering timeline
  custom, nessuna libreria di chart per l'MVP).
- **Storage**: SQLite (payload completi + colonne indicizzate) — vedi
  [schema](/interfaces/sqlite-schema.md).
- **Processo unico**: proxy + collector + UI in un solo processo Python
  sulla porta 8082 — vedi [architettura](/architecture.md).
- **Timeline verticale** (il tempo scorre verso il basso); i grafici
  classici (asse x = tempo) solo come vista opzionale futura.
- **Niente confronto side-by-side sincronizzato**; ogni sessione ha un
  suo URL così due sessioni si aprono in due tab. Il confronto fra run
  passa dai [tag di raccolta](/design/run-tagging.md).
- **Pausa del tempo**: LIVE ↔ PAUSA con scrubber su tutta la storia; i
  dati si raccolgono comunque, sempre.
- **Multi-sessione**: una alla volta in timeline, sidebar con elenco;
  subagenti annidati nella madre, cliccabili, con totali aggregati.
- **Click su qualunque evento** → pannello di dettaglio col payload
  completo.

# Rimandato / non nell'MVP

- Stima token per componente precisa (endpoint `count_tokens`) — oggi
  char/4, vedi [token accounting](/design/token-accounting.md).
- Grafico classico con tempo sulle ascisse (vista opzionale).
- Confronto affiancato di due run.
- Ricucitura della conversazione dopo `PreCompact`/compattazione.
- Animazioni avanzate (flussi, transizioni elaborate).

# Citations

[1] `PLAN.md` del repository — sezione "Decisioni prese con Sandro".
