# AgentSpy Hook

`agentspy_hook.py` is a Claude Code hook that sends session-event telemetry to
an agentspy collector. It reads the JSON payload Claude Code passes on stdin,
POSTs it to `/ingest/hook`, and is fire-and-forget: 2s timeout, errors ignored,
always exit 0.

Environment variables:

- `AGENTSPY_URL` — collector base URL (default `http://127.0.0.1:8082`);
- `AGENTSPY_TAG` — optional tag for the session;
- `AGENTSPY_DEBUG` — if `1`, print errors to stderr.

Setup, what each hook carries, and degraded mode: see
[../docs/hooks.md](../docs/hooks.md).
