# Design

* [Traffic ↔ session correlation](correlation.md) - How the proxy round trips (without a session_id) are assigned to sessions, turns and subagents — the most delicate part of the backend.
* [Collection tags to compare strategies](run-tagging.md) - A tag crosses both proxy (header) and hooks (env) to tell different runs apart in the UI — the mechanism for the educational comparison between strategies.
* [Token accounting and cost estimation](token-accounting.md) - Real usage from the API response for the totals; char/4 estimate for the per-component breakdown; educational pricing per model family.
* [Skill and slash-command recognition](skill-recognition.md) - How agentspy detects and quantifies skill usage in data it already captures — tool badge, turn trigger and a measure of the injected context.
* [Recognizing CLI service traffic](service-traffic.md) - The CLI spends model calls on its own machinery (safety, suggestions, titles, probes); each kind is told apart by discriminants read off the live DB, and named in the session title.
* [Adapter layers — provider and agent runtime](adapter-layers.md) - Two axes of specialization (providers/ for the LLM protocol, runtimes/ for the coding-agent conventions) behind which the backend's Anthropic/Claude Code knowledge is confined.
* [Architectural decisions (2026-07-07)](decisions.md) - Decisions taken with Sandro at the start of the project — stack, storage, timeline UX — and things explicitly deferred.
