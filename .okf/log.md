# Bundle Update Log

## 2026-07-25
* **Update**: `kimi` family (Moonshot) in the frontend — pink color, 256k window for K2 / 1M for K3, Moonshot kimi-k3 list prices in `pricing.ts` ([token accounting](/design/token-accounting.md), [frontend](/components/frontend.md)). Two new rows in the [agent × provider matrix](/runbooks/agent-provider-matrix.md) (Claude Code / opencode + Kimi via Moonshot, upstream `https://api.moonshot.ai/anthropic`, port 8084, status "to validate") plus a dedicated section; new "Kimi via Moonshot" section in [`docs/providers-and-gateways.md`](../docs/providers-and-gateways.md).
* **Update**: Bundle translated to English (full `.okf/` translation). `README-it.md` and `PLAN.md` removed from the repo; user-facing documentation restructured under `docs/` (slim README + thematic pages). Decisions previously kept in PLAN.md are preserved in [decisions](/design/decisions.md) and [architecture](/architecture.md).

## 2026-07-17
* **Creation**: [opencode plugin](/components/opencode-plugin.md) — second `AgentRuntime` (`runtimes/opencode.py` + `opencode_artifacts.py` + JS plugin), validated E2E: correlation to a single session, `callID` == `toolu_…`, artifacts split out of the system into a single block. Updated [adapter layers](/design/adapter-layers.md).
* **Creation**: [Agent × provider matrix](/runbooks/agent-provider-matrix.md) — the Claude Code/opencode × Anthropic/GLM-via-OpenRouter variants, with validation status and the OpenRouter emulation quirks (usage in the delta, `cost` field).
* **Update**: [Token accounting](/design/token-accounting.md) and [frontend](/components/frontend.md) — `glm` family (color, 200k/1M window, OpenRouter rates); collector: prompt usage accepted from `message_delta` only when `message_start` does not report it.

## 2026-07-16
* **Creation**: [Adapter layers — provider and agent runtime](/design/adapter-layers.md) — the backend's Anthropic/Claude Code knowledge confined to the specializable packages `providers/` and `runtimes/`; the persisted neutral model = the Anthropic shape. Updated [architecture](/architecture.md), [collector server](/components/collector-server.md), [correlation](/design/correlation.md), [skill recognition](/design/skill-recognition.md).
* **Deletion**: Standalone proxy (`agentspy_proxy.py` and its concept) — prototype removed from the repo; the [JSONL format](/interfaces/jsonl-log-format.md) stays documented as historical (the logs in `logs/` still serve as test fixtures).

## 2026-07-08
* **Update**: [frontend](/components/frontend.md) — dashboard polish: clicking on the charts opens the detail in place, session list and quick start box removed (the latter behind the "?" button in the sidebar footer), Claude/LLM bubble in the timeline turned green (`--c-llm` token).
* **Creation**: [Skill and slash-command recognition](/design/skill-recognition.md) — 🎓 badge for the `Skill` tool, turn trigger for slash-commands and a chip in the detail that measures the injected SKILL.md; updated [frontend](/components/frontend.md) (`utils/command.ts`, Skill icon, extended SystemReminderText).

## 2026-07-07
* **Update**: [Frontend](/components/frontend.md) — names of the two views (Charts = graphical dashboard, Timeline = interaction flow) and the sidebar button turned into a bidirectional toggle between the two; also documented the round-trip badge in the sidebar.
* **Initialization**: Created the OKF bundle by deriving it from README.md, PLAN.md and the source code.
* **Creation**: [Architecture](/architecture.md) with the three observation channels.
* **Creation**: Components — [collector server](/components/collector-server.md), [hook script](/components/hook-script.md), [MCP wrapper](/components/mcp-wrapper.md), [frontend](/components/frontend.md), standalone proxy (removed 2026-07-16), [seed demo](/components/seed-demo.md).
* **Creation**: Interfaces — [REST API](/interfaces/rest-api.md), [WebSocket](/interfaces/websocket.md), [ingest API](/interfaces/ingest-api.md), [SQLite schema](/interfaces/sqlite-schema.md), [JSONL format](/interfaces/jsonl-log-format.md).
* **Creation**: Design — [correlation](/design/correlation.md), [run tagging](/design/run-tagging.md), [token accounting](/design/token-accounting.md), [decisions](/design/decisions.md).
* **Creation**: Runbooks — [quickstart](/runbooks/quickstart.md), [development and testing](/runbooks/development.md).
