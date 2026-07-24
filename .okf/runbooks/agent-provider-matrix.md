---
type: Runbook
title: Agent × provider matrix — all setup variants
description: How to route the Claude Code/opencode × Anthropic/GLM-via-OpenRouter combinations through agentspy, what changes in each and what it takes to add new ones.
tags: [runbook, provider, runtime, openrouter, opencode, glm, kimi, moonshot]
timestamp: 2026-07-16T00:00:00Z
---

The rule that governs everything (see [adapter layers](/design/adapter-layers.md)):

- the **ProviderAdapter** depends on the endpoint's *wire format*, not on
  the model. As long as the traffic speaks Anthropic's Messages API — even
  through a compatible gateway such as OpenRouter — the provider is
  `anthropic`, whatever model runs on top (GLM included);
- the **AgentRuntime** depends on *who generates the traffic* (Claude
  Code, opencode…), not on where it goes.

Every agentspy instance has **one** upstream: to observe two upstreams in
parallel (e.g. Anthropic and OpenRouter) you launch two instances with a
dedicated port and DB, and point each agent (base URL + `AGENTSPY_URL` for
the hooks) at its own instance.

# Matrix

| Variant | Provider | Runtime | Upstream | Auth | Status |
|---------|----------|---------|----------|------|--------|
| Claude Code + Anthropic | `anthropic` | `claude-code` | `api.anthropic.com` (default) | subscription or `ANTHROPIC_API_KEY` | in use |
| Claude Code + GLM via OpenRouter | `anthropic` | `claude-code` | `https://openrouter.ai/api` | `ANTHROPIC_AUTH_TOKEN=$OPENROUTER_API_KEY` | validated E2E 2026-07-16 |
| Claude Code + Kimi via Moonshot | `anthropic` | `claude-code` | `https://api.moonshot.ai/anthropic` | `ANTHROPIC_AUTH_TOKEN=$MOONSHOT_API_KEY` | to validate |
| opencode + Anthropic | `anthropic` | `opencode` | `api.anthropic.com` (default) | metered `ANTHROPIC_API_KEY` (see ToS note) | validated E2E 2026-07-16 |
| opencode + GLM via OpenRouter | `anthropic` | `opencode` | `https://openrouter.ai/api` | `OPENROUTER_API_KEY` | to validate (combination of the two above) |
| opencode + Kimi via Moonshot | `anthropic` | `opencode` | `https://api.moonshot.ai/anthropic` | `MOONSHOT_API_KEY` | to validate |
| codex / OpenAI-format client | to be written | to be written | — | — | prospective |

**ToS note (2026)**: Claude Pro/Max subscriptions work ONLY inside Claude
Code — OAuth tokens in third-party tools are forbidden by the Anthropic
ToS (2026-02-19 update) and blocked server-side. With opencode the only
legitimate route to Claude models is a metered API key. Bridges/workarounds
(e.g. plugins that impersonate Claude Code) expose the account to
suspension.

# 1. Claude Code + Anthropic (standard setup)

See [quickstart](/runbooks/quickstart.md): the default instance on 8082,
`ANTHROPIC_BASE_URL=http://127.0.0.1:8082`.

# 2. Claude Code + GLM via OpenRouter

OpenRouter exposes an Anthropic-compatible endpoint (`/api/v1/messages`):
Claude Code talks to it natively, so the runtime and provider stay the
defaults. Only the instance upstream changes:

```bash
cd server && AGENTSPY_PORT=8083 AGENTSPY_UPSTREAM=https://openrouter.ai/api \
  AGENTSPY_DB=agentspy-openrouter.db uv run agentspy
```

For the agent launch functions (the `oclaude-spy` shell function with all
its exports) see
[`docs/providers-and-gateways.md`](../../docs/providers-and-gateways.md).

Everything else works unchanged: the hooks are the Claude Code ones,
`x-claude-code-session-id` still travels (the CLI sends it), the
`Authorization` header with the OpenRouter key is redacted before
persistence. The frontend recognizes the `glm` family (blue color, 200k
window for 4.x / 1M for 5.x, OpenRouter rates in `pricing.ts`).

OpenRouter emulation quirks observed in E2E (2026-07-16):

- `message_start` arrives with usage at **zero** and the real tokens are
  in `message_delta`: the collector accepts them from the delta only in
  this case (if `message_start` reports them, they stay frozen — see
  [token accounting](/design/token-accounting.md));
- `message_delta.usage` also carries the **real cost** in dollars
  (`cost`, `cost_details`): it is persisted in the payload, not yet used
  by the UI (which estimates from per-family rates).

# 3. opencode + Anthropic

You need the `opencode` runtime (`AGENTSPY_RUNTIME=opencode` on the
instance) and the ingest plugin on the opencode side: see
`hooks/opencode/README.md` for the installation (plugin +
`provider.anthropic.options.baseURL` pointed at the agentspy instance).
Auth: metered API key only.

# 4. opencode + GLM via OpenRouter

Same idea as variant 2 (the instance points at OpenRouter) + the
`opencode` runtime as in 3. The delicate point: opencode's *native*
`openrouter` provider speaks the OpenAI format, which agentspy does not
yet know how to interpret. Instead you must declare in `opencode.json` a
custom provider in **Anthropic format** (SDK `@ai-sdk/anthropic`) pointed
at the agentspy instance, with the GLM models:

```jsonc
{
  "provider": {
    "glm-spy": {
      "npm": "@ai-sdk/anthropic",
      "options": {
        "baseURL": "http://127.0.0.1:8083/v1",
        "apiKey": "{env:OPENROUTER_API_KEY}"
      },
      "models": { "z-ai/glm-5.2": {}, "z-ai/glm-4.7-flash": {} }
    }
  }
}
```

This way the wire format stays Messages API along the whole chain
(opencode → agentspy → OpenRouter) and agentspy's `anthropic` provider
keeps working. *To be validated in E2E: the custom-provider syntax and
passing the apiKey as the correct header.*

# 5. Kimi via Moonshot

Moonshot exposes an Anthropic-compatible endpoint
(`https://api.moonshot.ai/anthropic`), so this is the same scheme as variant 2
— only the upstream changes. The proxy concatenates `AGENTSPY_UPSTREAM` with
the request path, so no server change is needed.

```bash
cd server && AGENTSPY_PORT=8084 \
  AGENTSPY_UPSTREAM=https://api.moonshot.ai/anthropic \
  AGENTSPY_DB=agentspy-moonshot.db uv run agentspy
```

Models: `kimi-k3` (1M context) and the `kimi-k2-*` line (256k). This holds for
**both** runtimes — Claude Code (via the `kclaude-spy` launch function) and
opencode (via a custom Anthropic-format provider `kimi-spy` in `opencode.json`,
as in variant 4). A runtime is per instance, so spying on both in parallel
needs two instances. K3 is also on OpenRouter as `moonshotai/kimi-k3`, usable
from the 8083 instance with no new setup (the family regex covers the
vendor-prefixed id). For the launch functions and the opencode provider block
see [`docs/providers-and-gateways.md`](../../docs/providers-and-gateways.md).

# 6. codex / OpenAI-format client (prospective)

Here the wire format changes: it needs a new `ProviderAdapter` (a parser
for the Responses/Chat Completions API stream, normalizing blocks and
usage into the neutral model) plus an `AgentRuntime` for the client. It is
the "big" work described in [adapter layers](/design/adapter-layers.md);
none of the variants above require it.
