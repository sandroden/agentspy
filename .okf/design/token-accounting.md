---
type: Design Note
title: Token accounting and cost estimation
description: Real usage from the API response for the totals; char/4 estimate for the per-component breakdown; educational pricing per model family and per cache TTL.
tags: [token, usage, costs, cache]
timestamp: 2026-07-28T00:00:00Z
---

Two levels of precision, deliberate:

- **Real usage (exact)** — from the API response reconstructed from the
  SSE stream: `input_tokens`, `output_tokens`, `cache_read_tokens`,
  `cache_write_tokens` (5m/1h), thinking. It is the source for totals,
  context charts and costs.
- **Per-component estimate (approximate)** — `analyze_request_body()`
  breaks system/tools/messages down into characters and estimates the
  tokens as char/4. It serves the context-fill to show *what* the context
  is made of. Planned improvement: a `count_tokens` endpoint for
  precision.

# Cache write: the TTL is part of the data

A cache write is billed by the TTL it was made with: **5 minutes =
1.25×input**, **1 hour = 2×input**. The API reports the split in
`usage.cache_creation` (`ephemeral_5m_input_tokens` /
`ephemeral_1h_input_tokens`); `normalize_usage` promotes it to the
`cache_write_5m_tokens` / `cache_write_1h_tokens` columns. A provider that
doesn't report the tier leaves them **null** — "unknown tier", which stays
distinct from "0 tokens in that tier" and is priced at the cheaper 5m rate
so it can never inflate the estimate. `frontend/src/utils/cache.ts`
(`cacheWriteTiers`) derives the unknown share as
`cache_write - 5m - 1h`; charts and the TTL card read it from there.

Observed on the live DB (471 round trips): a round trip writes with one
TTL only, never both; **top-level Claude Code sessions write at 1h, Task
subagents at 5m**. Merging the two would have hidden both the strategy and
the cost.

# Cost estimation

`frontend/src/utils/pricing.ts` applies prices per model family
(educational values in $/Mtoken, not an official price list): opus
`{in 5, out 25, cache-read 0.5, cache-write 6.25 (5m) / 10 (1h)}`, sonnet
`{3, 15, 0.3, 3.75 / 6}`, haiku `{1, 5, 0.1, 1.25 / 2}`, fable = opus tier
(estimate), glm `{0.97, 3.06, 0.18, 0.97 / 0.97}` (OpenRouter rates for
glm-5.2, 2026-07; cache writes are not billed separately there, so both
tiers are charged as plain input; the flash variants are overestimated),
kimi `{3, 15, 0.3, 3 / 3}` (Moonshot kimi-k3 list prices, 2026-07; same
convention as glm; the K2 variants are approximated at this tier). Only
real data, no hypothetical projection.

# Aggregation

The subagents' tokens (child sessions) are aggregated into the parent
session (`get_sessions` computes the aggregates including recursive
descendants — see [SQLite schema](/interfaces/sqlite-schema.md)). The
"cumulative consumption" in the dashboard is the integral of the tokens
over time.
