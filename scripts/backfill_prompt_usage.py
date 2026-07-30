"""Backfill of prompt tokens (occupancy) on already captured round trips.

Context: until the SSE parser fix, ``SSECollector`` let ``message_delta``
overwrite the usage with a cumulative (throughput) ``cache_read_input_tokens``
on turns with extended thinking. The result: ``cache_read_tokens``/
``cache_write_tokens``/``input_tokens`` columns inflated with respect to the
real context window occupancy, with a phantom peak in the gauge.

The correct prompt value is in the ``message_start`` usage, which the proxy
saves anyway in ``payload.response.message.usage``. This script reads it back
and rewrites the prompt columns, leaving ``output_tokens`` alone (which is,
rightly, the final value from ``message_delta``).

Usage:

    uv run python scripts/backfill_prompt_usage.py            # dry-run (default)
    uv run python scripts/backfill_prompt_usage.py --apply    # actually writes
    uv run python scripts/backfill_prompt_usage.py -h
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

# prompt keys in the API usage -> DB columns
_PROMPT_COLS = {
    "input_tokens": "input_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
    "cache_creation_input_tokens": "cache_write_tokens",
}


def _message_start_usage(payload_json: str | None) -> dict | None:
    """The ``message_start`` usage = ``response.message.usage`` in the payload."""
    if not payload_json:
        return None
    try:
        payload = json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return None
    usage = ((payload.get("response") or {}).get("message") or {}).get("usage")
    return usage if isinstance(usage, dict) else None


def backfill(db_path: str, apply: bool) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, session_id, input_tokens, cache_read_tokens, cache_write_tokens, payload"
        " FROM events WHERE kind = 'round_trip'"
    ).fetchall()

    changed = 0
    for row in rows:
        usage = _message_start_usage(row["payload"])
        if usage is None:
            continue
        updates: dict[str, int] = {}
        for api_key, col in _PROMPT_COLS.items():
            new = usage.get(api_key)
            if new is None:
                continue
            if row[col] != new:
                updates[col] = new
        if not updates:
            continue
        changed += 1
        delta = row["cache_read_tokens"] - updates.get("cache_read_tokens", row["cache_read_tokens"])
        print(
            f"  event {row['id']} ({row['session_id'][:12]}): "
            f"cache_read {row['cache_read_tokens']} -> "
            f"{updates.get('cache_read_tokens', row['cache_read_tokens'])} (-{delta})"
        )
        if apply:
            sets = ", ".join(f"{col} = ?" for col in updates)
            conn.execute(
                f"UPDATE events SET {sets} WHERE id = ?",
                (*updates.values(), row["id"]),
            )

    if apply:
        conn.commit()
    conn.close()
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("db", nargs="?", default="server/agentspy.db", help="DB path (default: server/agentspy.db)")
    parser.add_argument("--apply", action="store_true", help="write the changes (without it, this is a dry-run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] backfill prompt usage on {args.db}")
    changed = backfill(args.db, args.apply)
    verb = "updated" if args.apply else "to update"
    print(f"{changed} round trips {verb}.")
    if changed and not args.apply:
        print("Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
