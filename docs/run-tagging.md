# Tagging runs

Tags let you separate different runs so you can compare strategies (e.g. with
and without a piece of context) in the UI.

```bash
ANTHROPIC_CUSTOM_HEADERS='x-agentspy-tag: con-okf' \
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 AGENTSPY_TAG=con-okf claude
```

The two variables carry the **same tag over two different channels**, and
converge on the same session `tag` field:

- `ANTHROPIC_CUSTOM_HEADERS` travels with the API traffic: Claude Code adds the
  `x-agentspy-tag` header to every request and the proxy applies it to the
  session it attributes the round trip to;
- `AGENTSPY_TAG` travels with the hooks: the script reads it from the
  environment and sends it to `/ingest/hook` (it also reaches the child
  sessions of subagents).

## Why two redundant channels

At steady state one is enough, as long as its channel is active: without
installed hooks the header is needed; with the proxy in the middle (always,
when spying) the header alone is sufficient. Setting both is zero-cost
redundancy that covers the edge cases:

- the header also tags processes that inherit the environment but have no hooks
  (e.g. a `claude -p` launched by an automation);
- the env also tags hook events of traffic not yet attributed by the
  correlator.

In the UI the tag distinguishes the collections; every session has its own URL
(`/ui/session/<id>`), so two runs open in two browser tabs.

## See also

- [Hooks](hooks.md) — the `AGENTSPY_TAG` channel.
- [Providers and gateways](providers-and-gateways.md) — tagging per upstream.
- [UI guide](ui-guide.md) — how the tag distinguishes collections in the UI.
- [`.okf/design/run-tagging.md`](../.okf/design/run-tagging.md) — internal
  design notes.
