---
type: Design Note
title: Token accounting and cost estimation
description: Real usage from the API response for the totals; char/4 estimate for the per-component breakdown; educational pricing per model family.
tags: [token, usage, costs, cache]
timestamp: 2026-07-07T00:00:00Z
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

# Cost estimation

`frontend/src/utils/pricing.ts` applies prices per model family
(educational values in $/Mtoken, not an official price list): opus
`{in 5, out 25, cache-read 0.5, cache-write 6.25}`, sonnet
`{3, 15, 0.3, 3.75}`, haiku `{1, 5, 0.1, 1.25}`, fable = opus tier
(estimate), glm `{0.97, 3.06, 0.18, 0.97}` (OpenRouter rates for
glm-5.2, 2026-07; the flash variants are overestimated). Only real data,
no hypothetical projection.

# Aggregation

The subagents' tokens (child sessions) are aggregated into the parent
session (`get_sessions` computes the aggregates including recursive
descendants — see [SQLite schema](/interfaces/sqlite-schema.md)). The
"cumulative consumption" in the dashboard is the integral of the tokens
over time.
