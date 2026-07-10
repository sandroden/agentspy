---
type: Design Note
title: Correlazione traffico ↔ sessioni
description: Come i round trip del proxy (senza session_id) vengono assegnati a sessioni, turni e subagenti — la parte più delicata del backend.
resource: server/agentspy_server/correlate.py
tags: [correlazione, sessioni, subagenti]
timestamp: 2026-07-07T00:00:00Z
---

Il traffico che attraversa il proxy non porta un `session_id`: il
`Correlator` (stato in-memory: `session_state`,
`fingerprint_to_session`, `tool_use_to_fingerprint`,
`prompt_to_session`) lo ricava con queste regole, in ordine di forza:

1. **tool_use_id** — l'hook `PreToolUse` porta `session_id` +
   `tool_use_id`; il round trip precedente conteneva il blocco
   `tool_use` con quell'id (`toolu_...`) → lega la conversazione API
   alla sessione hook, assorbendo l'eventuale sessione sintetica
   (`reassign_session` + broadcast `session_removed`).
2. **UserPromptSubmit** — avanza `turn_index += 1` in modo autoritativo;
   da quel momento `has_hooks=True` e l'euristica sul testo utente si
   disattiva. Il prompt è ricordato in `prompt_to_session` per legare
   conversazioni senza tool call.
3. **Fingerprint di conversazione** — sha256 di (system serializzato +
   primo messaggio user + `session_key`), con `_strip_volatile` che
   rimuove i marker `cache_control` (si spostano fra round trip). Il
   `session_key` è l'header `x-claude-code-session-id` (cli >= 2.x, su
   ogni richiesta, verificato presente al 100% e stabile entro una
   conversazione): senza di esso due run concorrenti con stesso system e
   stesso primo prompt collasserebbero nella stessa sessione sintetica.
   Stesso fingerprint → stessa sessione anche senza hook.
4. **Header `x-agentspy-tag`** — assegna il tag (vedi
   [run tagging](/design/run-tagging.md)).
5. **Subagenti** — schema reale verificato empiricamente (2026-07-07):
   gli hook generati *dentro* un subagente portano
   `agent_id`/`agent_type` ma il `session_id` **della madre**; l'evento
   va alla sessione figlia `sub-<agent_id>` (con `parent_session_id`),
   mentre `SubagentStart`/`SubagentStop` restano marker sulla timeline
   della madre.

# Degradazione senza hook

Sessioni sintetiche `syn-<fingerprint[:12]>` e turni euristici: nuovo
turno se l'ultimo messaggio user è testuale (non `tool_result`) e il
testo differisce dal precedente.

# Limiti noti

- Collisioni di fingerprint con prompt di test identici: risolte quando
  è presente `session_key` (header o session_id hook distinti). Senza
  header *e* senza hook (cli vecchia, nessun hook) due run identici
  restano indistinguibili: il proxy non ha alcuna informazione per
  separarli.
- Richieste fuori ordine (retry / parallelismo di Claude Code): si
  ordina per ts e si tollera l'out-of-order.
- `PreCompact`/compattazione: tracciata come evento, ma la ricucitura
  della conversazione compattata alla stessa sessione non è ancora
  gestita.
