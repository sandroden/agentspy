---
type: Web App
title: Frontend (Vue 3)
description: Interactive UI for live and replay — dashboard, vertical timeline by turn, context-fill and a tabbed detail panel.
resource: frontend/src
tags: [frontend, vue, vite, pinia, typescript]
timestamp: 2026-07-19T00:00:00Z
---

Stack: **Vue 3 + Vite + TypeScript + Pinia + vue-router**, no chart
library (custom SVG/DOM). Base path `/ui/`; in dev the Vite proxy
forwards `/api`, `/ingest`, `/ws` to `127.0.0.1:8082`.

```bash
cd frontend && npm run dev      # hot reload
cd frontend && npm run build    # vue-tsc + vite build → dist/ served on /ui
```

# Infrastructure

- `api/client.ts` — fetch to the [REST API](/interfaces/rest-api.md)
  (normalizes the Usage, recomputes the snippet for the detail) and
  `openStream()` on the [WebSocket](/interfaces/websocket.md) with
  backoff reconnection 1s→10s.
- `stores/spy.ts` (Pinia) — central state: sessions, events per session,
  cursor/live (time pause), selected event with a details cache, unseen
  badge. Getters `sessionTree` (parent/child tree) and `visibleEvents`
  (filtered by live/cursor). The player only navigates the steps that
  produce visible rows (`isPlayerStep`): with `showHooks` off (default,
  persisted in localStorage) the SessionStart/UserPromptSubmit/Stop hooks
  are skipped by `step`/`setCursor` — no "empty" clicks at the start of a
  human session; with the flag on every event is a step and the hooks
  render as markers.
- `router/index.ts` — `/` → DashboardView, `/session/:id` → SessionView
  (each session has its own URL, openable in another tab).
- `types.ts` — types mirroring the Python store shapes.

# Views and components

- **SessionHeader** (shared by Dashboard and Timeline): section header
  with the session name (tag, fallback to title/id), secondary title,
  live dot, sub-agent badge, meta row (model · duration · tokens · round
  trips) and the Timeline/Dashboard toggle on the right. Same body/weight
  as the **AgentSpy** brand in the sidebar (logo "A" + name in `App.vue`,
  with a WebSocket status dot), so the two headers align. In the
  dashboard it replaces the old identity bar: switching session changes
  the header itself.
- **MetricCards** (shared, `components/MetricCards.vue`): metric cards
  with emoji icons — peak context, tokens consumed (integral),
  consumption/peak, user prompts, round trips, sub-agents (🤖) and **cost
  estimate** from [token accounting](/design/token-accounting.md), plus
  the "+ sub-agents" group. Used by the dashboard and by the Timeline
  (`SessionSummaryBar`, replacing the old input/output/cache summary), so
  the "numbers" read the same across the two pages; the sub-agents card
  is clickable only in the dashboard (prop `clickableSubagents`).
- **DashboardView** (`/ui/`): the "featured" session — `SessionHeader` +
  `MetricCards`, `ContextChart` (context per round trip),
  `CompositionChart` (stacked area cache_read/write/input/output),
  `CumulativeChart` (token integral with drag selection), `SubagentBars`.
  The chart panels render on **dark cards** in both themes (the palette
  tokens are redefined on the container, so the SVG internals — grid,
  ticks, text, legends — adapt). Clicking a point on a chart **takes you
  to the Timeline** of the session, paused on that exact round trip and
  with the detail open (deep link `?event=<id>`, handled by SessionView);
  on the dashboard the right panel stays absent (gated on the route, it
  lives in the Timeline). The session list and the quick start are not in
  the dashboard: sessions live in the left sidebar, the quick start
  behind the "?" button at the bottom left.
- **SessionView**: `SessionHeader` (with the parent/subagent links as
  slots), vertical `TimelineView` grouped by turn (`TurnGroup`,
  `EventCard`, `HookMarker`, `McpCard`, `SubagentBlock`, `UsageBar`),
  `ContextFillPanel` (stacked bar per round trip), `TimeControls`
  (LIVE/PAUSE + scrubber, space and arrows, "⚓ hooks" toggle and an
  "event n/m" counter over the visible steps). `HookMarker` is the pill
  marker of a hook (visible only with the toggle on): it shows that
  Claude Code gave room for a reaction there (in the future: hooks that
  block tool calls) and clicking it opens the payload in the DetailPanel.
- **DetailPanel** (resizable right column, present only in the Timeline):
  header with the title "ROUND TRIP" + green pill `#n/total` and a
  monospace meta row; tabs Summary | Request | Response | Delta | JSON —
  the Summary includes a **donut** of the token distribution
  (cache_read/write/input/output, with % from cache) using theme
  variables; sub-components `ContentBlock`, `MessageBlock`, `JsonTree`,
  `SystemReminderText` (expanded/compact view of the `<system-reminder>`
  blocks **and of the skill invocations via slash-command**, persisted —
  see [skill & commands](/design/skill-recognition.md)).
- **SessionsSidebar**: at the top the **AgentSpy** brand (in `App.vue`)
  and the "Sessions" label; a tree list; each row shows tag + optional
  title (the session UUID is omitted — the tag identifies) and, on the
  right, the badge with the round-trip count that encodes its state:
  vivid while the session runs, gray once the Stop has arrived (no more
  LIVE chip). Plus the unseen badge. The toggle between the two views
  (`ViewToggle`, "🕐 Timeline | 📊 Dashboard") lives in the central
  area's `SessionHeader`: on "Timeline" it returns to the last opened
  session (`currentSessionId`, fallback `featuredSessionId`, disabled if
  both are null). In the dashboard, clicking a row does not navigate: it
  features the session in the charts. In the footer, the "?" (quick start
  modal) and ⚙️ Customize (light/dark theme) buttons.

The identity colors are CSS tokens in `App.vue`, redefined for the light
and dark themes: `--c-user` blue, `--c-tool` amber, `--c-llm` **green**
for the Claude/LLM bubble in the timeline, `--accent` for
selection/links.

# Utilities

- `utils/pricing.ts` — API cost estimate per model family (educational
  values in $/Mtoken; fable = opus tier; glm = OpenRouter rates).
- `utils/model.ts` — model family/color/abbreviation (including the
  non-Claude families seen via gateway, e.g. `z-ai/glm-5.2` → glm, blue).
- `utils/toolIcon.ts` — emoji per tool (Read 📄, Edit ✏️, Bash 💻, …;
  `Skill` → 🎓, `mcp__*` → 🔌).
- `utils/command.ts` — recognizes slash-commands / skills in user
  messages (see [skill & commands](/design/skill-recognition.md)).
- `utils/format.ts`, `composables/useElementSize.ts`.
