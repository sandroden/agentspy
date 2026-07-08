# Design

* [Correlazione traffico ↔ sessioni](correlation.md) - Come i round trip del proxy (senza session_id) vengono assegnati a sessioni, turni e subagenti — la parte più delicata del backend.
* [Tag di raccolta per confrontare strategie](run-tagging.md) - Un tag attraversa proxy (header) e hooks (env) per distinguere run diverse in UI — il meccanismo per il confronto didattico fra strategie.
* [Contabilità dei token e stima dei costi](token-accounting.md) - Usage reale dalla risposta API per i totali; stima char/4 per la scomposizione per componente; pricing didattico per famiglia di modello.
* [Riconoscimento di skill e slash-command](skill-recognition.md) - Come agentspy individua e quantifica l'uso di una skill nei dati già catturati — badge tool, trigger di turno e misura del contesto iniettato.
* [Decisioni architetturali (2026-07-07)](decisions.md) - Decisioni prese con Sandro all'avvio del progetto — stack, storage, UX della timeline — e cose esplicitamente rimandate.
