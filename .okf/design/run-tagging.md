---
type: Design Note
title: Collection tags to compare strategies
description: A tag crosses both proxy (header) and hooks (env) to tell different runs apart in the UI — the mechanism for the educational comparison between strategies.
tags: [tag, comparison, teaching]
timestamp: 2026-07-07T00:00:00Z
---

A central educational goal of the project: comparing how the context is
used across different strategies (e.g. with and without a knowledge
bundle). The mechanism is a **collection tag** that travels over two
parallel channels:

- **Proxy**: the `x-agentspy-tag` header injected with
  `ANTHROPIC_CUSTOM_HEADERS`, read by
  [correlation](/design/correlation.md) (rule 4);
- **Hooks**: the `AGENTSPY_TAG` env read by the
  [hook script](/components/hook-script.md).

# Examples

```bash
ANTHROPIC_CUSTOM_HEADERS='x-agentspy-tag: con-okf' \
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 AGENTSPY_TAG=con-okf claude
```

In the UI the tag distinguishes the collections; each session has its own
URL (`/ui/session/<id>`), so two runs are compared by opening them in two
browser tabs (the synchronized side-by-side comparison was explicitly
deferred, see [decisions](/design/decisions.md)).
