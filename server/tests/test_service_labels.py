"""Recognition of CLI service traffic.

The cases below are not invented: each corresponds to a shape actually measured
on the live DB (see the table in .okf/design/service-traffic.md). The negative
case is the important one — a real conversation shares its system prompt with
the suggestions, and must never end up labelled.
"""

import pytest

from agentspy_server.runtimes.claude_code import ClaudeCodeRuntime
from agentspy_server.store import Store

def title_of(store, session_id):
    """Title as recorded (Store exposes the sessions as a list)."""
    return next(s["title"] for s in store.get_sessions() if s["id"] == session_id)


BILLING = {"type": "text", "text": "x-anthropic-billing-header: cc_version=2.1.219.076;"}
SECURITY = "You are a security monitor for autonomous AI coding agents.\n\n## Context\n\n…"
CLAUDE_CODE = "You are Claude Code, Anthropic's official CLI for Claude.\n\n# Harness\n…"
AGENT_SDK = "You are a Claude agent, built on Anthropic's Claude Agent SDK.\n…"


def body(system=None, *, max_tokens=64000, stop=None, messages=None):
    """Request in the shape Claude Code sends: system as a list of blocks, with
    the billing header ALWAYS first — the prompt is never at offset 0."""
    out = {"max_tokens": max_tokens, "messages": messages or []}
    if system is not None:
        out["system"] = [BILLING, {"type": "text", "text": system}]
    if stop is not None:
        out["stop_sequences"] = stop
    return out


def user(text):
    return [{"role": "user", "content": [{"type": "text", "text": text}]}]


@pytest.mark.parametrize(
    "case, request_body, expected",
    [
        (
            "security stage 1: grades the harm, stops at the severity tag",
            body(SECURITY, max_tokens=64, stop=["</severity>"]),
            "security 1",
        ),
        (
            "security stage 2: weighs user intent, stops at the block tag",
            body(SECURITY, max_tokens=64, stop=["</block>"]),
            "security 2",
        ),
        (
            "security variant without a stop sequence: stays generic, not forced",
            body(SECURITY, max_tokens=8192),
            "security monitor",
        ),
        ("Agent SDK traffic", body(AGENT_SDK), "agent sdk"),
        ("probe: one output token", body(None, max_tokens=1, messages=user("quota")), "quota"),
        (
            "suggestions: same prompt as a conversation, told apart by the marker",
            body(CLAUDE_CODE, messages=user("[SUGGESTION MODE: Suggest what the user might…]")),
            "suggestions",
        ),
        (
            "title generation: the conversation wrapped in <session>",
            body(CLAUDE_CODE, messages=user("<session>\nping\n</session>\n\nWrite the title in ita")),
            "title",
        ),
        (
            "real conversation: NOT service traffic",
            body(CLAUDE_CODE, messages=user("ping")),
            None,
        ),
        (
            "conversation merely mentioning the marker deep in the transcript",
            body(CLAUDE_CODE, messages=user("x" * 400 + "[SUGGESTION MODE")),
            None,
        ),
        ("system as a plain string", body(None, messages=[]) | {"system": SECURITY}, "security monitor"),
        ("malformed body", None, None),
        ("empty body", {}, None),
    ],
)
def test_service_label(case, request_body, expected):
    assert ClaudeCodeRuntime().service_label(request_body) == expected, case


def test_other_runtimes_may_ignore_the_question():
    """The base contract returns None: a runtime is not required to know."""
    from agentspy_server.runtimes.opencode import OpencodeRuntime

    assert OpencodeRuntime().service_label(body(SECURITY, stop=["</severity>"])) is None


# -- persistence: the label must not regress -------------------------------


def _round_trip(store, session_id, request_body, ts):
    store.insert_event(
        session_id=session_id,
        kind="round_trip",
        turn_index=1,
        ts_start=ts,
        ts_end=ts + 1,
        payload={"request": {"body": request_body}, "response": {}},
    )


def test_weak_title_never_overwrites_a_recognized_one(tmp_path):
    """The marker is not on every round trip (measured: 11 of 13): the generic
    label must not drag the session back."""
    store = Store(tmp_path / "weak.db")
    store.upsert_session("syn-1", title="suggestions", started_at=1.0)
    store.upsert_session("syn-1", title="service", title_weak=True, started_at=2.0)
    assert title_of(store, "syn-1") == "suggestions"

    # a strong title still wins, otherwise the label could never be corrected
    store.upsert_session("syn-1", title="security 1", started_at=3.0)
    assert title_of(store, "syn-1") == "security 1"
    store.close()


def test_weak_title_fills_an_empty_field(tmp_path):
    store = Store(tmp_path / "fill.db")
    store.upsert_session("syn-2", started_at=1.0)
    store.upsert_session("syn-2", title="service", title_weak=True, started_at=2.0)
    assert title_of(store, "syn-2") == "service"
    store.close()


def test_backfill_relabels_existing_sessions(tmp_path):
    """Sessions already recorded as generic are relabelled at startup, reading
    the payload that has always held the discriminant."""
    db = tmp_path / "backfill.db"
    store = Store(db)
    store.upsert_session("syn-3", title="service", started_at=1.0)
    # first round trip unrecognizable, the second carries the marker: scanning
    # in order, the session must still end up labelled
    _round_trip(store, "syn-3", body(CLAUDE_CODE, messages=user("no marker here")), 1.0)
    _round_trip(store, "syn-3", body(CLAUDE_CODE, messages=user("[SUGGESTION MODE: …]")), 2.0)
    store.upsert_session("syn-4", title="service", started_at=1.0)
    _round_trip(store, "syn-4", body(SECURITY, max_tokens=64, stop=["</block>"]), 1.0)
    # a real session must be left alone
    store.upsert_session("real", tag="demo", started_at=1.0)
    _round_trip(store, "real", body(CLAUDE_CODE, messages=user("ping")), 1.0)
    store.close()

    reopened = Store(db)  # the migration runs on open
    assert title_of(reopened, "syn-3") == "suggestions"
    assert title_of(reopened, "syn-4") == "security 2"
    assert title_of(reopened, "real") is None
    reopened.close()

    # idempotent: reopening changes nothing
    again = Store(db)
    assert title_of(again, "syn-3") == "suggestions"
    again.close()


@pytest.mark.parametrize("order", ["generic first", "specific first"])
def test_family_label_never_wins_over_the_stage(tmp_path, order):
    """Measured on the live DB: a monitor session holds 43 round trips at
    `</block>` PLUS one with no stop sequence. The family-only label must not
    make the name depend on which one is scanned first."""
    db = tmp_path / f"family-{order.replace(' ', '-')}.db"
    store = Store(db)
    store.upsert_session("syn-6", title="service", started_at=1.0)
    variants = [
        body(SECURITY, max_tokens=8192),  # family only: "security monitor"
        body(SECURITY, max_tokens=64, stop=["</block>"]),  # the stage
    ]
    if order == "specific first":
        variants.reverse()
    for i, request_body in enumerate(variants):
        _round_trip(store, "syn-6", request_body, 1.0 + i)
    store.close()

    reopened = Store(db)
    assert title_of(reopened, "syn-6") == "security 2"
    reopened.close()


def test_ingest_and_backfill_agree_on_the_family_label(tmp_path):
    """Same rule on the live path: a weak family label fills the field but is
    then superseded by the stage, in either order."""
    store = Store(tmp_path / "ingest.db")
    store.upsert_session("syn-7", title="security monitor", title_weak=True, started_at=1.0)
    store.upsert_session("syn-7", title="security 2", started_at=2.0)
    assert title_of(store, "syn-7") == "security 2"

    store.upsert_session("syn-8", title="security 2", started_at=1.0)
    store.upsert_session("syn-8", title="security monitor", title_weak=True, started_at=2.0)
    assert title_of(store, "syn-8") == "security 2"
    store.close()


def test_backfill_survives_a_malformed_payload(tmp_path):
    """A non-JSON payload must not stop the migration (nor startup)."""
    db = tmp_path / "malformed.db"
    store = Store(db)
    store.upsert_session("syn-5", title="service", started_at=1.0)
    _round_trip(store, "syn-5", body(SECURITY, max_tokens=64, stop=["</severity>"]), 2.0)
    store.close()

    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO events (session_id, kind, ts_start, payload) VALUES (?,?,?,?)",
                 ("syn-5", "round_trip", 1.0, "not json at all"))
    conn.commit()
    conn.close()

    reopened = Store(db)
    assert title_of(reopened, "syn-5") == "security 1"
    reopened.close()
