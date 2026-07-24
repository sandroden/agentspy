# opencode

Plugin to spy on [opencode](https://opencode.ai) traffic to the Anthropic API
with agentspy. Two channels, as for Claude Code:

- the **proxy** captures the HTTP round trips (system prompt, tools, messages)
  — opencode points at it by setting the Anthropic provider's `baseURL`;
- the **plugin** (`agentspy.js`) sends the runtime's native events
  (`chat.message`, `tool.execute.before/after`, `session.idle`) to the ingest
  API, for session and turn correlation.

> Authentication: **metered API key only** (`ANTHROPIC_API_KEY`). This plugin
> does not use and does not require any OAuth bridge.

## 1. agentspy server with the opencode runtime

Start the server selecting the opencode runtime (the default would be
`claude-code`):

```bash
AGENTSPY_RUNTIME=opencode <agentspy server start command>
```

The runtime declares the opencode vocabulary (native hook names, no session
header) used by correlation and artifact extraction.

## 2. opencode configuration

opencode must be configured (in `opencode.json`, project or global) to:

1. forward Anthropic requests to the agentspy proxy;
2. load the plugin.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["/ABSOLUTE/PATH/agentspy/hooks/opencode/agentspy.js"],
  "provider": {
    "anthropic": {
      "options": {
        "baseURL": "http://127.0.0.1:8082/v1"
      }
    }
  }
}
```

### Why `/v1` in the baseURL

The `@ai-sdk/anthropic` provider (the one opencode uses underneath) defaults to
`https://api.anthropic.com/v1` and POSTs to `${baseURL}/messages`. opencode
passes the config `baseURL` verbatim to the `createAnthropic` factory, without
adding anything. So to hit the proxy on the path it expects (`/v1/messages`,
the same as Anthropic) the `baseURL` **must include `/v1`**:
`http://127.0.0.1:8082/v1`. Omitting it would send requests to
`http://127.0.0.1:8082/messages`.

> Do not rely on the `ANTHROPIC_BASE_URL` environment variable:
> `@ai-sdk/anthropic` reads it verbatim and, if set without `/v1`, returns 404.
> Better to declare an explicit `options.baseURL` in `opencode.json`.

As an alternative to the `"plugin"` field, you can leave the file in
`.opencode/plugin/agentspy.js` (in the project root or in
`~/.config/opencode/`): opencode auto-loads plugins from that folder.

## 3. Plugin environment variables

Read by the plugin at runtime (on the opencode side):

| Variable | Default | Use |
|----------|---------|-----|
| `AGENTSPY_URL` | `http://127.0.0.1:8082` | base URL of the agentspy server (ingest is `${AGENTSPY_URL}/ingest/hook`) |
| `AGENTSPY_TAG` | *(none)* | optional tag to group/filter sessions |

## Known limits (honest mapping)

The tool is educational: the data reflects the reality of the runtime,
including the grey areas not yet verifiable without real traffic.

- **End of turn.** `session.idle` is mapped to `hook_stop`: like Claude Code's
  `Stop` it fires at the end of every assistant response, not only at the end
  of the session. The session goes "live" again on the next `chat.message` or
  tool.
- **Main session correlation — verified (E2E 2026-07-16).** opencode does not
  send a header with the session id on the HTTP requests: the round trip ↔ real
  session link goes through *prompt-binding* (text of the last user message ==
  `prompt` of a `chat.message`) and the join by `tool_use_id`. In E2E the
  session comes out correctly unique (`ses_…` with coherent round trips, hooks
  and turns). The theoretical edge case remains of a `chat.message` arriving
  *after* the round trip (slow/down ingest): there you would see a split
  session (round trip under `syn-<fingerprint>`).
- **`callID` == `toolu_…` — confirmed (E2E 2026-07-16).** The `callID` that
  opencode passes to the tool hooks IS the `toolu_…` id from the Anthropic wire:
  the `tool_use_id → session` join works as with Claude Code. Not yet verified
  is the passing of the id in the `_meta` of **MCP** tools/call
  (`mcp_tool_use_id_key` stays empty until observed).
- **Subagents.** opencode runs subagents as child sessions (via the `task`
  tool, distinguished by a `parentID`), without dedicated start/stop hooks like
  Claude Code. Subagent correlation is not yet implemented: a subagent's events
  currently stay on the session it was launched from.

## See also

- [Providers and gateways](providers-and-gateways.md) — the agent × provider
  matrix (opencode + Anthropic / GLM rows).
- [`.okf/components/opencode-plugin.md`](../.okf/components/opencode-plugin.md)
  — internal notes on the plugin.
- [`.okf/design/adapter-layers.md`](../.okf/design/adapter-layers.md) — the
  runtime adapter design.
