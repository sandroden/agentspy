---
type: Design Note
title: Contabilità dei token e stima dei costi
description: Usage reale dalla risposta API per i totali; stima char/4 per la scomposizione per componente; pricing didattico per famiglia di modello.
tags: [token, usage, costi, cache]
timestamp: 2026-07-07T00:00:00Z
---

Due livelli di precisione, deliberati:

- **Usage reale (esatto)** — dalla risposta API ricostruita dallo
  stream SSE: `input_tokens`, `output_tokens`, `cache_read_tokens`,
  `cache_write_tokens` (5m/1h), thinking. È la fonte per totali,
  grafici di contesto e costi.
- **Stima per componente (approssimata)** — `analyze_request_body()`
  scompone system/tools/messages in caratteri e stima i token come
  char/4. Serve al context-fill per mostrare *di cosa è fatto* il
  contesto. Miglioramento previsto: endpoint `count_tokens` per la
  precisione.

# Stima dei costi

`frontend/src/utils/pricing.ts` applica prezzi per famiglia di modello
(valori didattici in $/Mtoken, non tariffario ufficiale): opus
`{in 5, out 25, cache-read 0.5, cache-write 6.25}`, sonnet
`{3, 15, 0.3, 3.75}`, haiku `{1, 5, 0.1, 1.25}`, fable = fascia opus
(stima), glm `{0.97, 3.06, 0.18, 0.97}` (tariffe OpenRouter di glm-5.2,
2026-07; le varianti flash sono sovrastimate). Solo dati reali, nessuna
proiezione ipotetica.

# Aggregazione

I token dei subagenti (sessioni figlie) sono aggregati nella sessione
madre (`get_sessions` calcola gli aggregati inclusi i discendenti
ricorsivi — vedi [schema SQLite](/interfaces/sqlite-schema.md)). Il
"consumo cumulativo" in dashboard è l'integrale dei token nel tempo.
