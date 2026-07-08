"""Backfill dei token di prompt (occupancy) sui round trip già catturati.

Contesto: fino al fix del parser SSE, ``SSECollector`` lasciava che
``message_delta`` sovrascrivesse la usage con un ``cache_read_input_tokens``
cumulativo (throughput) sui turni con extended thinking. Il risultato: colonne
``cache_read_tokens``/``cache_write_tokens``/``input_tokens`` gonfiate rispetto
all'occupancy reale della finestra di contesto, con un picco fantasma nel gauge.

Il valore corretto del prompt è nella usage di ``message_start``, che il proxy
salva comunque in ``payload.response.message.usage``. Questo script la rilegge e
riscrive le colonne di prompt, lasciando ``output_tokens`` (che è, giustamente,
il valore finale del ``message_delta``).

Uso:

    uv run python scripts/backfill_prompt_usage.py            # dry-run (default)
    uv run python scripts/backfill_prompt_usage.py --apply    # scrive davvero
    uv run python scripts/backfill_prompt_usage.py -h
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

# chiavi del prompt nella usage dell'API -> colonne del DB
_PROMPT_COLS = {
    "input_tokens": "input_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
    "cache_creation_input_tokens": "cache_write_tokens",
}


def _message_start_usage(payload_json: str | None) -> dict | None:
    """La usage di ``message_start`` = ``response.message.usage`` nel payload."""
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
    parser.add_argument("db", nargs="?", default="server/agentspy.db", help="path del DB (default: server/agentspy.db)")
    parser.add_argument("--apply", action="store_true", help="scrive le modifiche (senza, è un dry-run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] backfill prompt usage su {args.db}")
    changed = backfill(args.db, args.apply)
    verb = "aggiornati" if args.apply else "da aggiornare"
    print(f"{changed} round trip {verb}.")
    if changed and not args.apply:
        print("Rilancia con --apply per scrivere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
