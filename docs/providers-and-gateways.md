# Providers and gateways

agentspy separates two concerns:

- the **provider** depends on the *wire format* of the endpoint, not on the
  model. As long as the traffic speaks the Anthropic Messages API — even
  through a compatible gateway such as OpenRouter — the provider is
  `anthropic`, whatever model runs on top (GLM included);
- the **runtime** depends on *who generates the traffic* (Claude Code,
  opencode…), not on where it goes.

## One instance, one upstream

Every agentspy instance has **one** upstream. To observe two upstreams in
parallel (e.g. Anthropic and OpenRouter) you run two instances with a
dedicated port and DB each, and point every agent (base URL + `AGENTSPY_URL`
for the hooks) at its own instance.

Port / DB convention:

- **8082** — Anthropic (default instance, `./agentspy.db`);
- **8083** — OpenRouter (`agentspy-openrouter.db`);
- **8084** — Moonshot (`agentspy-moonshot.db`);
- other combinations use their own dedicated port and DB.

## The matrix

| Variant | Provider | Runtime | Upstream | Auth |
|---------|----------|---------|----------|------|
| Claude Code + Anthropic | `anthropic` | `claude-code` | `api.anthropic.com` (default) | subscription or `ANTHROPIC_API_KEY` |
| Claude Code + GLM via OpenRouter | `anthropic` | `claude-code` | `https://openrouter.ai/api` | `ANTHROPIC_AUTH_TOKEN=$OPENROUTER_API_KEY` |
| Claude Code + Kimi via Moonshot | `anthropic` | `claude-code` | `https://api.moonshot.ai/anthropic` | `ANTHROPIC_AUTH_TOKEN=$MOONSHOT_API_KEY` |
| opencode + Anthropic | `anthropic` | `opencode` | `api.anthropic.com` (default) | metered `ANTHROPIC_API_KEY` (see ToS note) |
| opencode + GLM via OpenRouter | `anthropic` | `opencode` | `https://openrouter.ai/api` | `OPENROUTER_API_KEY` |
| opencode + Kimi via Moonshot | `anthropic` | `opencode` | `https://api.moonshot.ai/anthropic` | `MOONSHOT_API_KEY` |

**ToS note (2026):** Claude Pro/Max subscriptions work ONLY inside Claude Code
— OAuth tokens in third-party tools are forbidden by the Anthropic ToS
(2026-02-19 update) and blocked server-side. With opencode the only legitimate
route to Claude models is a metered API key. Bridges/workarounds (e.g. plugins
that impersonate Claude Code) expose the account to suspension.

## Claude Code + Anthropic (standard setup)

The default instance on 8082, `ANTHROPIC_BASE_URL=http://127.0.0.1:8082`. See
[Installation](installation.md) and [Run tagging](run-tagging.md).

## Claude Code + GLM via OpenRouter

OpenRouter exposes an Anthropic-compatible endpoint (`/api/v1/messages`):
Claude Code talks to it natively, so runtime and provider stay the defaults.
Only the instance upstream changes:

```bash
cd server && AGENTSPY_PORT=8083 AGENTSPY_UPSTREAM=https://openrouter.ai/api \
  AGENTSPY_DB=agentspy-openrouter.db uv run agentspy
```

Launch function (spy variant of a plain `oclaude`):

```bash
oclaude-spy () {
  ( export ANTHROPIC_BASE_URL="http://127.0.0.1:8083"
    export ANTHROPIC_API_KEY=""
    export ANTHROPIC_AUTH_TOKEN="$OPENROUTER_API_KEY"
    export ANTHROPIC_MODEL="z-ai/glm-5.2"
    export ANTHROPIC_SMALL_FAST_MODEL="z-ai/glm-4.7-flash"
    export AGENTSPY_URL="http://127.0.0.1:8083"
    export ANTHROPIC_CUSTOM_HEADERS="x-agentspy-tag: glm"   # tag on proxy traffic
    claude )
}
```

Everything else works unchanged: the hooks are the Claude Code ones,
`x-claude-code-session-id` still travels (the CLI sends it), and the
`Authorization` header with the OpenRouter key is redacted before
persistence. The frontend recognizes the `glm` family (blue color, 200k window
for 4.x / 1M for 5.x, OpenRouter rates in `pricing.ts`).

OpenRouter emulation quirks observed in E2E (2026-07-16):

- `message_start` arrives with usage at **zero** and the real tokens are in
  `message_delta`: the collector accepts them from the delta only in this case
  (if `message_start` reports them they stay frozen);
- `message_delta.usage` also carries the **real cost** in dollars (`cost`,
  `cost_details`): it is persisted in the payload, not yet used by the UI
  (which estimates from per-family rates).

## Kimi via Moonshot

Moonshot exposes an Anthropic-compatible endpoint
(`https://api.moonshot.ai/anthropic`, `…/anthropic/v1/messages`), so the exact
same scheme as OpenRouter applies — only the upstream changes. Kimi K3
(`kimi-k3`, 2026-07-16) has a 1M context; the K2 line
(`kimi-k2-thinking-turbo` …) has 256k.

Direct use (no spy), for reference:

```bash
kclaude () {
  ( export ANTHROPIC_BASE_URL=https://api.moonshot.ai/anthropic
    export ANTHROPIC_AUTH_TOKEN=${MOONSHOT_API_KEY}
    export ANTHROPIC_MODEL=kimi-k2-thinking-turbo        # or kimi-k3
    export ANTHROPIC_DEFAULT_OPUS_MODEL=$ANTHROPIC_MODEL
    export ANTHROPIC_DEFAULT_SONNET_MODEL=$ANTHROPIC_MODEL
    export ANTHROPIC_DEFAULT_HAIKU_MODEL=$ANTHROPIC_MODEL
    export CLAUDE_CODE_SUBAGENT_MODEL=$ANTHROPIC_MODEL
    claude )
}
```

Dedicated spy instance (the proxy concatenates `AGENTSPY_UPSTREAM` with the
request path, so no server change is needed):

```bash
cd server && AGENTSPY_PORT=8084 \
  AGENTSPY_UPSTREAM=https://api.moonshot.ai/anthropic \
  AGENTSPY_DB=agentspy-moonshot.db uv run agentspy
```

Launch function (spy variant of `kclaude`, mirror of `oclaude-spy`):

```bash
kclaude-spy () {
  ( export ANTHROPIC_BASE_URL="http://127.0.0.1:8084"
    export ANTHROPIC_API_KEY=""
    export ANTHROPIC_AUTH_TOKEN=${MOONSHOT_API_KEY}
    export ANTHROPIC_MODEL=kimi-k2-thinking-turbo        # or kimi-k3
    export ANTHROPIC_DEFAULT_OPUS_MODEL=$ANTHROPIC_MODEL
    export ANTHROPIC_DEFAULT_SONNET_MODEL=$ANTHROPIC_MODEL
    export ANTHROPIC_DEFAULT_HAIKU_MODEL=$ANTHROPIC_MODEL
    export CLAUDE_CODE_SUBAGENT_MODEL=$ANTHROPIC_MODEL
    export AGENTSPY_URL="http://127.0.0.1:8084"
    export ANTHROPIC_CUSTOM_HEADERS="x-agentspy-tag: kimi"   # tag on proxy traffic
    claude )
}
```

The frontend recognizes the `kimi` family (pink color, 256k window for K2 /
1M for K3, Moonshot rates in `pricing.ts`).

### opencode + Kimi

Same as the GLM variant: opencode's native providers speak the OpenAI format,
which agentspy does not yet parse, so declare a custom provider in **Anthropic
format** (SDK `@ai-sdk/anthropic`) in `opencode.json`, pointed at the agentspy
instance:

```jsonc
{
  "provider": {
    "kimi-spy": {
      "npm": "@ai-sdk/anthropic",
      "options": {
        "baseURL": "http://127.0.0.1:8084/v1",
        "apiKey": "{env:MOONSHOT_API_KEY}"
      },
      "models": { "kimi-k3": {}, "kimi-k2-thinking-turbo": {} }
    }
  }
}
```

The 8084 instance must run with `AGENTSPY_RUNTIME=opencode`. A runtime is per
instance, so to spy on Claude Code **and** opencode against Moonshot in
parallel you need two instances (two ports, two DBs). See
[opencode](opencode.md) for the full runtime and plugin setup.

Note: K3 is also on OpenRouter as `moonshotai/kimi-k3`, so it can be observed
from the existing 8083 instance with no new setup — the family regex covers the
vendor-prefixed id.

Both Moonshot variants are **to validate E2E**.

## opencode + Anthropic

Needs the `opencode` runtime (`AGENTSPY_RUNTIME=opencode` on the instance) and
the ingest plugin on the opencode side. Auth: metered API key only. See
[opencode](opencode.md) for the full setup.

## opencode + GLM via OpenRouter

Same idea as the OpenRouter variant above (the instance points at OpenRouter)
plus the `opencode` runtime. The delicate point: opencode's *native*
`openrouter` provider speaks the OpenAI format, which agentspy does not yet
parse. Instead, declare a custom provider in **Anthropic format** (SDK
`@ai-sdk/anthropic`) in `opencode.json`, pointed at the agentspy instance, with
the GLM models. See [opencode](opencode.md).

## See also

- [opencode](opencode.md) — the opencode runtime and plugin setup in full.
- [Run tagging](run-tagging.md) — tagging runs to compare strategies.
- [`.okf/runbooks/agent-provider-matrix.md`](../.okf/runbooks/agent-provider-matrix.md)
  — the internal runbook with all variants, including future prospects.
- [`.okf/design/adapter-layers.md`](../.okf/design/adapter-layers.md) — the
  provider/runtime adapter design.
