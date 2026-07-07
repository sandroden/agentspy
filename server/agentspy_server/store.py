"""Persistenza SQLite (WAL) per sessioni ed eventi.

Un'unica connessione condivisa, protetta da un lock: gli scenari di scrittura
attesi (proxy + hooks + mcp di una singola sessione di lavoro didattica) non
giustificano un pool o uno scheduler dedicato. Il lock serializza anche le
letture per semplicità: il volume di traffico è quello di un solo sviluppatore
al lavoro, non un servizio multi-utente.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    tag TEXT,
    title TEXT,
    model TEXT,
    parent_session_id TEXT,
    agent_id TEXT,
    started_at REAL,
    ended_at REAL,
    live INTEGER,
    cwd TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    kind TEXT,
    subkind TEXT,
    turn_index INTEGER,
    agent_id TEXT,
    ts_start REAL,
    ts_end REAL,
    ttfb_s REAL,
    model TEXT,
    status INTEGER,
    stop_reason TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    tool_names TEXT,
    payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_session_ts ON events(session_id, ts_start);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
CREATE INDEX IF NOT EXISTS idx_events_turn ON events(turn_index);
"""


def default_db_path() -> str:
    return os.environ.get("AGENTSPY_DB", "./agentspy.db")


def _snippet_from_payload(kind: str, subkind: str | None, payload: dict | None) -> str:
    """Estrae un breve testo rappresentativo per le liste evento (best-effort)."""
    if not payload:
        return ""
    try:
        if kind == "round_trip":
            message = (payload.get("response") or {}).get("message") or {}
            for block in message.get("content") or []:
                if block.get("type") == "text" and block.get("text"):
                    return block["text"][:160]
                if block.get("type") == "tool_use":
                    return f"tool_use: {block.get('name')}"
            body = (payload.get("request") or {}).get("body") or {}
            messages = body.get("messages") or []
            if messages:
                content = messages[-1].get("content")
                if isinstance(content, str):
                    return content[:160]
            return ""
        if kind == "hook":
            # schema hook reale: UserPromptSubmit porta "prompt",
            # Pre/PostToolUse portano "tool_name"
            prompt = payload.get("prompt")
            if isinstance(prompt, str) and prompt:
                return prompt[:160]
            tool_name = payload.get("tool_name")
            if isinstance(tool_name, str) and tool_name:
                return tool_name
            return subkind or ""
        if kind == "mcp":
            return subkind or ""
    except Exception:
        return ""
    return ""


def _tool_hint(name: str | None, tool_input: Any) -> str:
    """Indizio compatto dell'argomento di una chiamata tool, per i badge in
    timeline: path per i tool su file, inizio comando per Bash, url/query per
    i tool web, pattern per le ricerche. Best-effort, stringa vuota se non
    riconosciuto."""
    if not isinstance(tool_input, dict):
        return ""
    try:
        for key in ("file_path", "notebook_path", "path"):
            v = tool_input.get(key)
            if isinstance(v, str) and v:
                return v
        if name == "Bash":
            v = tool_input.get("command")
        elif name in ("Grep", "Glob"):
            v = tool_input.get("pattern")
        elif name == "WebFetch":
            v = tool_input.get("url")
        elif name == "WebSearch":
            v = tool_input.get("query")
        elif name in ("Task", "Agent"):
            v = tool_input.get("description") or tool_input.get("prompt")
        elif name == "Skill":
            v = tool_input.get("skill")
        else:
            # fallback generico (incluso mcp__*): il primo valore stringa
            v = next((x for x in tool_input.values() if isinstance(x, str) and x), None)
        if isinstance(v, str):
            v = " ".join(v.split())  # su una riga
            return v[:200]
    except Exception:
        pass
    return ""


def _tool_uses_from_payload(payload: dict | None) -> list[dict[str, str]]:
    """Coppie {name, hint} dai blocchi tool_use della risposta di un round trip."""
    if not payload:
        return []
    try:
        message = (payload.get("response") or {}).get("message") or {}
        out = []
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name") or "?"
                out.append({"name": name, "hint": _tool_hint(name, block.get("input"))})
        return out
    except Exception:
        return []


class Store:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path) if db_path is not None else default_db_path()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(SCHEMA)
            # migrazione leggera per DB creati prima della colonna cwd
            try:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN cwd TEXT")
            except sqlite3.OperationalError:
                pass
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- sessions -----------------------------------------------------

    def upsert_session(
        self,
        id: str,
        *,
        tag: str | None = None,
        title: str | None = None,
        model: str | None = None,
        parent_session_id: str | None = None,
        agent_id: str | None = None,
        started_at: float | None = None,
        ended_at: float | None = None,
        live: bool | None = None,
        cwd: str | None = None,
    ) -> None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE id=?", (id,)).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO sessions (id, tag, title, model, parent_session_id, agent_id,"
                    " started_at, ended_at, live, cwd) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        id, tag, title, model, parent_session_id, agent_id,
                        started_at, ended_at, 1 if live is None else int(live), cwd,
                    ),
                )
            else:
                starts = [v for v in (row["started_at"], started_at) if v is not None]
                ends = [v for v in (row["ended_at"], ended_at) if v is not None]
                new_started = min(starts) if starts else None
                new_ended = max(ends) if ends else None
                self._conn.execute(
                    "UPDATE sessions SET tag=COALESCE(?, tag), title=COALESCE(?, title),"
                    " model=COALESCE(?, model), parent_session_id=COALESCE(?, parent_session_id),"
                    " agent_id=COALESCE(?, agent_id), started_at=?, ended_at=?,"
                    " live=COALESCE(?, live), cwd=COALESCE(?, cwd) WHERE id=?",
                    (
                        tag, title, model, parent_session_id, agent_id, new_started, new_ended,
                        None if live is None else int(live), cwd, id,
                    ),
                )
            self._conn.commit()

    def reassign_session(self, old_id: str, new_id: str) -> int:
        """Sposta tutti gli eventi di ``old_id`` sotto ``new_id`` e assorbe la
        riga di sessione (usato quando una sessione sintetica creata dal solo
        traffico proxy viene identificata con una sessione reale via hook).
        Ritorna il numero di eventi riassegnati."""
        with self._lock:
            old = self._conn.execute("SELECT * FROM sessions WHERE id=?", (old_id,)).fetchone()
            cur = self._conn.execute(
                "UPDATE events SET session_id=? WHERE session_id=?", (new_id, old_id)
            )
            moved = cur.rowcount
            # Gli eventi arrivati quando la sessione era ancora sintetica
            # portano il turn_index di QUELLO stato (spesso 0): senza questo
            # ricalcolo finirebbero nel gruppo "pre-prompt" invece che nel
            # turno del prompt che li ha innescati. Il turno giusto è quello
            # dell'ultimo UserPromptSubmit della sessione reale che precede
            # l'evento; se non ce n'è (traffico pre-prompt, o sessione
            # subagente senza prompt) il turn_index resta com'era.
            self._conn.execute(
                """
                UPDATE events SET turn_index = COALESCE(
                    (SELECT MAX(h.turn_index) FROM events h
                     WHERE h.session_id = ? AND h.kind = 'hook'
                       AND h.subkind = 'UserPromptSubmit'
                       AND h.ts_start <= events.ts_start),
                    turn_index)
                WHERE session_id = ? AND kind = 'round_trip'
                """,
                (new_id, new_id),
            )
            self._conn.execute("DELETE FROM sessions WHERE id=?", (old_id,))
            self._conn.commit()
        if old is not None:
            # fonde i metadati della vecchia riga (started_at min, ended_at
            # max, tag/model se mancanti) nella sessione di destinazione.
            self.upsert_session(
                new_id,
                tag=old["tag"],
                model=old["model"],
                started_at=old["started_at"],
                ended_at=old["ended_at"],
            )
        return moved

    def delete_sessions(self, ids: list[str]) -> list[str]:
        """Elimina le sessioni indicate e TUTTE le loro discendenti (subagenti,
        ricorsivamente via parent_session_id), cancellando prima gli eventi e
        poi le righe di sessione. Gli id inesistenti vengono ignorati. Ritorna
        l'elenco completo (dedup) degli id effettivamente eliminati."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, parent_session_id FROM sessions"
            ).fetchall()
            children: dict[str | None, list[str]] = {}
            existing: set[str] = set()
            for r in rows:
                existing.add(r["id"])
                children.setdefault(r["parent_session_id"], []).append(r["id"])

            to_delete: list[str] = []
            seen: set[str] = set()

            def collect(sid: str) -> None:
                if sid in seen or sid not in existing:
                    return
                seen.add(sid)
                to_delete.append(sid)
                for c in children.get(sid, []):
                    collect(c)

            for sid in ids:
                collect(sid)

            if not to_delete:
                return []

            placeholders = ",".join("?" for _ in to_delete)
            self._conn.execute(
                f"DELETE FROM events WHERE session_id IN ({placeholders})", to_delete
            )
            self._conn.execute(
                f"DELETE FROM sessions WHERE id IN ({placeholders})", to_delete
            )
            self._conn.commit()
        return to_delete

    # -- events ---------------------------------------------------------

    def insert_event(
        self,
        *,
        session_id: str | None,
        kind: str,
        subkind: str | None = None,
        turn_index: int | None = None,
        agent_id: str | None = None,
        ts_start: float | None = None,
        ts_end: float | None = None,
        ttfb_s: float | None = None,
        model: str | None = None,
        status: int | None = None,
        stop_reason: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        tool_names: list[str] | None = None,
        payload: dict | None = None,
    ) -> int:
        tool_names_json = json.dumps(tool_names or [])
        payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (session_id, kind, subkind, turn_index, agent_id, ts_start,"
                " ts_end, ttfb_s, model, status, stop_reason, input_tokens, output_tokens,"
                " cache_read_tokens, cache_write_tokens, tool_names, payload)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id, kind, subkind, turn_index, agent_id, ts_start, ts_end, ttfb_s,
                    model, status, stop_reason, input_tokens, output_tokens, cache_read_tokens,
                    cache_write_tokens, tool_names_json, payload_json,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    # -- read side --------------------------------------------------------

    def get_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = [
                dict(r)
                for r in self._conn.execute("SELECT * FROM sessions ORDER BY started_at").fetchall()
            ]
            agg_rows = self._conn.execute(
                # turn_index 0 = eventi pre-turno (SessionStart, traffico di
                # servizio): non è un turno utente e non va contato.
                "SELECT session_id,"
                " COUNT(DISTINCT CASE WHEN turn_index >= 1 THEN turn_index END) AS turns,"
                " SUM(CASE WHEN kind='round_trip' THEN 1 ELSE 0 END) AS round_trips,"
                " MIN(ts_start) AS min_ts, MAX(COALESCE(ts_end, ts_start)) AS max_ts,"
                " SUM(COALESCE(input_tokens,0)) AS input_tokens,"
                " SUM(COALESCE(output_tokens,0)) AS output_tokens,"
                " SUM(COALESCE(cache_read_tokens,0)) AS cache_read_tokens,"
                " SUM(COALESCE(cache_write_tokens,0)) AS cache_write_tokens"
                " FROM events GROUP BY session_id"
            ).fetchall()
        own_agg = {r["session_id"]: dict(r) for r in agg_rows}

        children: dict[str | None, list[str]] = {}
        for s in sessions:
            children.setdefault(s["parent_session_id"], []).append(s["id"])

        def descendants(sid: str) -> list[str]:
            out = []
            for c in children.get(sid, []):
                out.append(c)
                out.extend(descendants(c))
            return out

        result = []
        for s in sessions:
            agg = own_agg.get(s["id"], {})
            usage = {
                "input_tokens": agg.get("input_tokens", 0) or 0,
                "output_tokens": agg.get("output_tokens", 0) or 0,
                "cache_read_tokens": agg.get("cache_read_tokens", 0) or 0,
                "cache_write_tokens": agg.get("cache_write_tokens", 0) or 0,
            }
            usage_incl = dict(usage)
            for child_id in descendants(s["id"]):
                child_agg = own_agg.get(child_id, {})
                for k in usage_incl:
                    usage_incl[k] += child_agg.get(k, 0) or 0
            duration_s = None
            if agg.get("min_ts") is not None and agg.get("max_ts") is not None:
                duration_s = agg["max_ts"] - agg["min_ts"]
            result.append(
                {
                    "id": s["id"],
                    "tag": s["tag"],
                    "title": s["title"],
                    "model": s["model"],
                    "parent_session_id": s["parent_session_id"],
                    "agent_id": s["agent_id"],
                    "started_at": s["started_at"],
                    "ended_at": s["ended_at"],
                    "live": bool(s["live"]),
                    "cwd": s["cwd"],
                    "turns": agg.get("turns") or 0,
                    "round_trips": agg.get("round_trips") or 0,
                    "duration_s": duration_s,
                    "usage": usage,
                    "usage_incl_children": usage_incl,
                }
            )
        return result

    def _event_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload"]) if row["payload"] else None
        duration_s = None
        if row["ts_end"] is not None and row["ts_start"] is not None:
            duration_s = row["ts_end"] - row["ts_start"]
        return {
            "id": row["id"],
            "kind": row["kind"],
            "subkind": row["subkind"],
            "session_id": row["session_id"],
            "turn_index": row["turn_index"],
            "agent_id": row["agent_id"],
            "ts_start": row["ts_start"],
            "duration_s": duration_s,
            "ttfb_s": row["ttfb_s"],
            "model": row["model"],
            "status": row["status"],
            "stop_reason": row["stop_reason"],
            "usage": {
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "cache_read_tokens": row["cache_read_tokens"],
                "cache_write_tokens": row["cache_write_tokens"],
            },
            "tool_names": json.loads(row["tool_names"]) if row["tool_names"] else [],
            "tool_uses": _tool_uses_from_payload(payload) if row["kind"] == "round_trip" else [],
            "tool_hint": (
                _tool_hint((payload or {}).get("tool_name"), (payload or {}).get("tool_input"))
                if row["kind"] == "hook" and row["subkind"] in ("PreToolUse", "PostToolUse")
                else ""
            ),
            "snippet": _snippet_from_payload(row["kind"], row["subkind"], payload),
        }

    def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        """Summary leggeri (senza il campo payload) ordinati per ts_start."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY ts_start", (session_id,)
            ).fetchall()
            return [self._event_summary(r) for r in rows]

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        """Riga evento completa, con payload e tool_names deserializzati."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["payload"] = json.loads(d["payload"]) if d["payload"] else None
        d["tool_names"] = json.loads(d["tool_names"]) if d["tool_names"] else []
        return d

    def get_session_stats(self, session_id: str) -> list[dict[str, Any]]:
        """Serie per round trip (turn_index, timing, token, char-estimate) per il context-fill."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE session_id=? AND kind='round_trip' ORDER BY ts_start",
                (session_id,),
            ).fetchall()
        stats = []
        for row in rows:
            payload = json.loads(row["payload"]) if row["payload"] else {}
            analysis = (payload.get("request") or {}).get("analysis") or {}
            stats.append(
                {
                    "event_id": row["id"],
                    "turn_index": row["turn_index"],
                    "ts_start": row["ts_start"],
                    "ttfb_s": row["ttfb_s"],
                    "duration_s": (row["ts_end"] - row["ts_start"])
                    if (row["ts_end"] is not None and row["ts_start"] is not None)
                    else None,
                    "model": row["model"],
                    "input_tokens": row["input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "cache_read_tokens": row["cache_read_tokens"],
                    "cache_write_tokens": row["cache_write_tokens"],
                    "system_chars": analysis.get("system_chars"),
                    "tools_chars": (analysis.get("tools") or {}).get("chars"),
                    "messages_chars": (analysis.get("messages") or {}).get("chars"),
                }
            )
        return stats
