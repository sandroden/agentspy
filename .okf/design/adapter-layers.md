---
type: Design
title: Adapter layers — provider and agent runtime
description: Two axes of specialization (providers/ for the LLM protocol, runtimes/ for the coding-agent conventions) behind which all of the backend's Anthropic/Claude Code knowledge is confined.
tags: [design, extensibility, provider, runtime]
timestamp: 2026-07-16T00:00:00Z
---

The backend's coupling to "Claude Code talking to Anthropic" lives on two
independent axes, each confined in a specializable package with a
registry + environment variable:

| Layer | Package | Isolates | Selection |
|-------|---------|----------|-----------|
| Provider | `server/agentspy_server/providers/` | the LLM API's wire protocol: what a model call is, body analysis, reconstruction from the SSE stream, usage field names | `AGENTSPY_PROVIDER` (default `anthropic`) |
| Agent runtime | `server/agentspy_server/runtimes/` | the coding-agent conventions: session header, hook names, MCP bridge, real last user message, tool hints, slash-command snippet, context artifacts | `AGENTSPY_RUNTIME` (default `claude-code`) |

Supporting **opencode with Anthropic models** = a new `AgentRuntime` —
done: `runtimes/opencode.py` + [ingest plugin](/components/opencode-plugin.md),
validated E2E on 2026-07-16. Supporting **codex/OpenAI** = a new
`ProviderAdapter` (Responses API parser) + a new `AgentRuntime`. The
concrete combinations are in the
[agent × provider matrix](/runbooks/agent-provider-matrix.md).

# The neutral model is the Anthropic shape

Key decision: the internal model that is persisted and rendered — content
blocks `text|thinking|tool_use|tool_result|image`, usage with neutral
names (`input_tokens`, `output_tokens`, `cache_read_tokens`,
`cache_write_tokens` plus the TTL split `cache_write_5m_tokens` /
`cache_write_1h_tokens`, null when the provider doesn't report it) in the
DB columns — is deliberately **derived from
Anthropic's Messages API**. Consequences:

- for Anthropic the translation is ~identity → the DBs already captured
  stay valid with no migration;
- the frontend (which dispatches on `block.type` and reads the usage
  columns) does not change: a new provider *translates* its wire format
  into this model at ingest time, inside `StreamCollector.finalize()` and
  `normalize_usage()`;
- the raw request body stays persisted as it was passed over the wire: it
  is the educational material, it is not normalized away.

# Interfaces

`ProviderAdapter` (providers/base.py): `is_model_call(path, body)`,
`analyze_request(body)`, `stream_collector()`, `json_response_summary(body)`,
`normalize_usage(usage)`. The `ProxyForwarder` stays pure
provider-agnostic transport; the emitted record carries the `provider`
field.

`AgentRuntime` (runtimes/base.py): a declarative vocabulary
(`session_id_header`, `hook_user_prompt`, `hook_pre/post_tool_use`,
`hook_subagent_start/stop`, `hook_stop`, `mcp_tool_use_id_key`,
`system_reminder_prefix`) + derived helpers (`is_session_end`,
`is_subagent_hook`, `is_tool_call_hook`, `tool_use_id_from_mcp_meta`,
`is_system_reminder`) + abstract parsers (`last_user_message`,
`tool_hint`, `command_snippet`, `extract_artifacts`) + one concrete
parser with a default, `extract_artifact_content(body, key)` (the content
of a single artifact, for the reader in the UI: returns `None` — "not
available" — for a runtime that does not implement it). The Claude Code
artifact inventory (formerly `context_artifacts.py`) is now
`runtimes/claude_code_artifacts.py`, an implementation detail of
`ClaudeCodeRuntime`.

The split between inventory and content is deliberate:
`extract_artifacts` runs for **every** round trip of a session (events and
stats) and must stay light — identity + size only; the content, which can
be a whole file or a base64 image, is re-read from the body only when the
user opens it (`GET /api/events/{id}/artifact`).

# Runtime layer boundaries

- The **hook payload field names** (`session_id`, `prompt`,
  `tool_use_id`, `tool_name`, `agent_id`…) do NOT go through the runtime:
  they are the neutral format of the [ingest API](/interfaces/ingest-api.md).
  For an agent whose native events have a different shape, the
  translation is the job of the agent-side hook script/plugin, not the
  server.
- The *generic* [correlation](/design/correlation.md) heuristics (sha256
  fingerprint, synthetic sessions, structural turn detection) stay in the
  `Correlator`; from the runtime it only takes the vocabulary.
- The **frontend** is not (yet) parameterized: model families, context
  windows, pricing, tool icons remain Claude-centric tables in
  `frontend/src/utils/` — extensible, but outside these layers.

# Citations

[1] `server/agentspy_server/providers/base.py` — the neutral model's contract and rationale.
[2] `server/agentspy_server/runtimes/base.py` — the runtime layer's contract and boundaries.
