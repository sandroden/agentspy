---
type: Design Note
title: Tag di raccolta per confrontare strategie
description: Un tag attraversa proxy (header) e hooks (env) per distinguere run diverse in UI — il meccanismo per il confronto didattico fra strategie.
tags: [tag, confronto, didattica]
timestamp: 2026-07-07T00:00:00Z
---

Obiettivo didattico centrale del progetto: confrontare l'impiego del
contesto fra strategie diverse (es. con e senza un bundle di
conoscenza). Il meccanismo è un **tag di raccolta** che viaggia su due
canali paralleli:

- **Proxy**: header `x-agentspy-tag` iniettato con
  `ANTHROPIC_CUSTOM_HEADERS`, letto dalla
  [correlazione](/design/correlation.md) (regola 4);
- **Hooks**: env `AGENTSPY_TAG` letta dallo
  [hook script](/components/hook-script.md).

# Examples

```bash
ANTHROPIC_CUSTOM_HEADERS='x-agentspy-tag: con-okf' \
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 AGENTSPY_TAG=con-okf claude
```

In UI il tag distingue le raccolte; ogni sessione ha il suo URL
(`/ui/session/<id>`), quindi due run si confrontano aprendole in due
tab del browser (il confronto affiancato sincronizzato è stato
esplicitamente rimandato, vedi [decisioni](/design/decisions.md)).
