---
type: Design Note
title: Recognizing CLI service traffic
description: The CLI spends model calls on its own machinery (safety, suggestions, titles, probes); each kind is told apart by discriminants read off the live DB, and named in the session title.
tags: [service, sessions, recognition, teaching]
timestamp: 2026-07-31T00:00:00Z
---

A synthetic session bound to a real parent is not a conversation: it is the
CLI spending model calls on itself. Until now they all showed up as `service`
in the sidebar, which hid the fact that they do very different jobs — one
watches the agent, another suggests what to type, another just probes. The
request already says which is which: the runtime knows the prompts
([adapter layers](/design/adapter-layers.md)).

# Discriminants

Measured on the live DB (624 round trips), never guessed. Encoded in
`ClaudeCodeRuntime.service_label`:

| label | discriminant | measured |
|---|---|---|
| `security 1` | system opens with `You are a security monitor…` + `stop_sequences: ["</severity>"]` | 94 rt / 5 sessions |
| `security 2` | same prompt + `stop_sequences: ["</block>"]` | 85 rt / 3 sessions |
| `security monitor` | same prompt, no stop sequence (variant not forced into either stage) | 1 rt |
| `suggestions` | `[SUGGESTION MODE` opening a message block | 34 rt / 18 sessions |
| `title` | the conversation wrapped in `<session>…</session>` | 8 sessions |
| `agent sdk` | system opens with `You are a Claude agent, built on…Agent SDK` | 16 rt / 8 sessions |
| `quota` | `max_tokens: 1` (the body is literally `"quota"`) | 16 rt / 5 sessions |

The two safety stages are the prompt's own vocabulary, not our naming: *"Stage
1 does NOT apply user intent or ALLOW exceptions — stage 2 will handle
those."* Stage 1 grades harm and answers `<severity>N</severity>` on a 0-100
scale where 50 is the block threshold; `max_tokens: 64` with the stop sequence
gives round trips of 9 output tokens.

The system prompt is matched **block by block**, not on the concatenation:
Claude Code sends `system` as a list whose first block is the billing header,
so the prompt that identifies the traffic is never at offset 0.

# Why the generic label survives

Two kinds are indistinguishable from a real conversation by their system
prompt (`You are Claude Code…`) — suggestions and title generation — and are
recognized only by a marker in the messages. That marker **is not on every
round trip**: measured 11 out of 13 on a suggestions session. Two consequences:

- `upsert_session(title_weak=True)` — the generic label fills the field but
  never overwrites a sharper one already found. Without it the first
  unrecognizable round trip would drag the session back to `service`.
- The backfill scans a session's round trips **in chronological order** and
  the first label found wins; stopping at the first round trip would give an
  order-dependent result.

The same problem shows up **inside** the safety family: `security monitor` (no
stop sequence) says which family the traffic belongs to, not which stage, and
it coexists with the sharper variant in the same session — measured on
`syn-866e1c0072ca`: 43 round trips at `</block>` plus one with no stop
sequence. It is therefore declared in `generic_service_labels`: weak like the
fallback, so it fills the field but is superseded by the stage. Ingest and
backfill apply the same rule, so a session gets the same name whether it was
labelled live or relabelled later.

What stays unrecognized stays unrecognized on purpose: a synthetic session not
yet bound to its parent carries a normal conversation, byte for byte
(measured: payloads of 400-800 KB opening with `<system-reminder>`). Inventing
a label for it would be worse than the generic one.

# Backfill

`_migrate_service_labels_locked` at store startup, same pattern as the other
two migrations ([SQLite schema](/interfaces/sqlite-schema.md)): additive,
idempotent, guarded by `json_valid(payload)`, restricted to sessions still
carrying a generic title. Generic means `service` **or** `servizio`: the label
was written in Italian before the UI was translated and a live DB holds both.

Measured on a copy of a real DB (155 MB, 2026-07-28): 0.6 s, 12 of 15 service
sessions relabelled (8 `title`, 3 `security 2`, 1 `quota`), the other 3
left generic because they are the unrecognizable case above. Sessions with a
real title (`Explore`, tags) are not touched. The cost of later starts is
proportional to what is left unrecognized, not to the DB.

# Limits

- Recognition is by prefix on the prompts and by marker: a rewording of the
  opening words of a service prompt makes the traffic fall back to `service`
  (degradation, not an error).
- The `sub-agent` badge in the UI is `!!parent_session_id`, so it still covers
  both real Task subagents and these synthetic sessions — a separate concern
  from the label, see the TTL note in
  [token accounting](/design/token-accounting.md).
