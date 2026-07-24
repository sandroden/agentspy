# agentspy for opencode

`agentspy.js` is an [opencode](https://opencode.ai) plugin that sends the
runtime's native events (`chat.message`, `tool.execute.before/after`,
`session.idle`) to the agentspy ingest API, for session and turn correlation.
The proxy captures the HTTP round trips separately (opencode points at it via
the Anthropic provider's `baseURL`, which must include `/v1`).

Authentication: metered API key only (`ANTHROPIC_API_KEY`); no OAuth bridge.

Full setup (server runtime, `opencode.json`, environment variables, known
limits): see [../../docs/opencode.md](../../docs/opencode.md).
