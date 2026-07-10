import stat

from agentspy_server.store import Store


def test_db_file_permissions_are_owner_only(tmp_path):
    """Il DB può contenere prompt/risposte in chiaro: deve nascere 0600."""
    db_path = tmp_path / "perms.db"
    store = Store(db_path)
    store.upsert_session("s1", started_at=1.0)
    mode = stat.S_IMODE(db_path.stat().st_mode)
    assert mode == 0o600
    store.close()


def test_insert_and_get_event(tmp_path):
    store = Store(tmp_path / "test.db")
    store.upsert_session("s1", tag="demo", model="claude-x", started_at=100.0, ended_at=105.0, live=True)
    event_id = store.insert_event(
        session_id="s1",
        kind="round_trip",
        turn_index=0,
        ts_start=100.0,
        ts_end=102.0,
        ttfb_s=0.5,
        model="claude-x",
        status=200,
        stop_reason="end_turn",
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=0,
        cache_write_tokens=0,
        tool_names=["Bash"],
        payload={
            "request": {"body": {}},
            "response": {"message": {"content": [{"type": "text", "text": "ciao"}]}},
        },
    )
    assert isinstance(event_id, int)

    events = store.get_session_events("s1")
    assert len(events) == 1
    assert events[0]["id"] == event_id
    assert "payload" not in events[0]
    assert events[0]["snippet"] == "ciao"
    assert events[0]["usage"]["input_tokens"] == 10
    assert events[0]["tool_names"] == ["Bash"]

    full = store.get_event(event_id)
    assert full["payload"]["response"]["message"]["content"][0]["text"] == "ciao"
    assert full["tool_names"] == ["Bash"]

    assert store.get_event(event_id + 1) is None
    store.close()


def test_sessions_aggregate_with_children(tmp_path):
    store = Store(tmp_path / "test2.db")
    store.upsert_session("parent", started_at=0.0, ended_at=10.0, live=True)
    store.upsert_session(
        "child", parent_session_id="parent", agent_id="explorer", started_at=2.0, ended_at=8.0, live=True
    )

    store.insert_event(
        session_id="parent",
        kind="round_trip",
        turn_index=0,
        ts_start=0.0,
        ts_end=1.0,
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )
    store.insert_event(
        session_id="child",
        kind="round_trip",
        turn_index=0,
        ts_start=3.0,
        ts_end=4.0,
        input_tokens=20,
        output_tokens=10,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )

    sessions = store.get_sessions()
    by_id = {s["id"]: s for s in sessions}

    assert by_id["parent"]["usage"]["input_tokens"] == 100
    assert by_id["parent"]["usage_incl_children"]["input_tokens"] == 120
    assert by_id["parent"]["usage_incl_children"]["output_tokens"] == 60
    assert by_id["child"]["usage"]["input_tokens"] == 20
    assert by_id["child"]["usage_incl_children"]["input_tokens"] == 20
    assert by_id["child"]["parent_session_id"] == "parent"
    store.close()


def test_upsert_session_merges_started_ended(tmp_path):
    store = Store(tmp_path / "test3.db")
    store.upsert_session("s1", started_at=10.0, ended_at=10.0, live=True)
    store.upsert_session("s1", started_at=5.0, ended_at=20.0, live=True)
    sessions = {s["id"]: s for s in store.get_sessions()}
    assert sessions["s1"]["started_at"] == 5.0
    assert sessions["s1"]["ended_at"] == 20.0
    store.close()


def test_session_stats(tmp_path):
    store = Store(tmp_path / "test4.db")
    store.upsert_session("s1", started_at=0.0, live=True)
    store.insert_event(
        session_id="s1",
        kind="round_trip",
        turn_index=0,
        ts_start=0.0,
        ts_end=1.0,
        ttfb_s=0.2,
        input_tokens=10,
        output_tokens=4,
        cache_read_tokens=0,
        cache_write_tokens=0,
        payload={
            "request": {
                "body": {},
                "analysis": {"system_chars": 100, "tools": {"chars": 200}, "messages": {"chars": 30}},
            },
            "response": {},
        },
    )
    stats = store.get_session_stats("s1")
    assert len(stats) == 1
    assert stats[0]["system_chars"] == 100
    assert stats[0]["tools_chars"] == 200
    assert stats[0]["messages_chars"] == 30
    store.close()


def test_delete_sessions_cascade(tmp_path):
    store = Store(tmp_path / "del1.db")
    store.upsert_session("parent", started_at=0.0, live=True)
    store.upsert_session("child", parent_session_id="parent", started_at=1.0, live=True)
    store.upsert_session("grandchild", parent_session_id="child", started_at=2.0, live=True)
    store.upsert_session("other", started_at=0.0, live=True)

    store.insert_event(session_id="parent", kind="round_trip", ts_start=0.0)
    store.insert_event(session_id="child", kind="hook", subkind="PreToolUse", ts_start=1.0)
    store.insert_event(session_id="grandchild", kind="round_trip", ts_start=2.0)
    store.insert_event(session_id="other", kind="round_trip", ts_start=0.0)

    deleted = store.delete_sessions(["parent"])
    assert set(deleted) == {"parent", "child", "grandchild"}

    ids = {s["id"] for s in store.get_sessions()}
    assert ids == {"other"}
    # gli eventi delle sessioni cancellate spariscono
    assert store.get_session_events("parent") == []
    assert store.get_session_events("child") == []
    assert store.get_session_events("grandchild") == []
    assert len(store.get_session_events("other")) == 1
    store.close()


def test_delete_sessions_ignores_unknown_and_dedups(tmp_path):
    store = Store(tmp_path / "del2.db")
    store.upsert_session("a", started_at=0.0, live=True)
    store.upsert_session("b", parent_session_id="a", started_at=1.0, live=True)

    # id inesistente ignorato; padre + figlio elencati esplicitamente non
    # producono duplicati.
    deleted = store.delete_sessions(["a", "b", "nope"])
    assert sorted(deleted) == ["a", "b"]
    assert deleted.count("b") == 1

    assert store.get_sessions() == []
    assert store.delete_sessions(["nope"]) == []
    store.close()


def test_reassign_session(tmp_path):
    from agentspy_server.store import Store

    store = Store(str(tmp_path / "t.db"))
    store.upsert_session("syn-abc", tag="run-X", started_at=100.0, ended_at=110.0)
    store.upsert_session("real-1", started_at=105.0, ended_at=120.0)
    e1 = store.insert_event(session_id="syn-abc", kind="round_trip", ts_start=101.0,
                            input_tokens=10, output_tokens=5)
    e2 = store.insert_event(session_id="real-1", kind="hook", subkind="PreToolUse", ts_start=106.0)

    moved = store.reassign_session("syn-abc", "real-1")
    assert moved == 1

    sessions = store.get_sessions()
    ids = [s["id"] for s in sessions]
    assert "syn-abc" not in ids and "real-1" in ids
    real = next(s for s in sessions if s["id"] == "real-1")
    # metadati fusi: started_at minimo, tag ereditato
    assert real["started_at"] == 100.0
    assert real["tag"] == "run-X"

    events = store.get_session_events("real-1")
    assert {e["id"] for e in events} == {e1, e2}
    store.close()


def test_tool_hints_in_summary(tmp_path):
    from agentspy_server.store import Store

    store = Store(str(tmp_path / "t.db"))
    store.upsert_session("s1", started_at=1.0, cwd="/home/x/progetto")
    rt = store.insert_event(
        session_id="s1", kind="round_trip", ts_start=2.0,
        payload={"response": {"message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/home/x/progetto/src/a.py"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls  -la\n | head"}},
        ]}}},
    )
    hook = store.insert_event(
        session_id="s1", kind="hook", subkind="PreToolUse", ts_start=3.0,
        payload={"tool_name": "WebFetch", "tool_input": {"url": "https://example.com/x"}},
    )
    events = {e["id"]: e for e in store.get_session_events("s1")}
    assert events[rt]["tool_uses"] == [
        {"name": "Read", "hint": "/home/x/progetto/src/a.py"},
        {"name": "Bash", "hint": "ls -la | head"},  # normalizzato su una riga
    ]
    assert events[hook]["tool_hint"] == "https://example.com/x"
    # il cwd della sessione è esposto (serve alla UI per relativizzare i path)
    assert store.get_sessions()[0]["cwd"] == "/home/x/progetto"
    store.close()


def test_command_snippet_in_input_snippet(tmp_path):
    """Un messaggio user che espande uno slash-command / skill dà uno snippet
    pulito `/nome args`, non l'XML del wrapper né lo SKILL.md iniettato."""
    from agentspy_server.store import Store

    store = Store(str(tmp_path / "t.db"))
    store.upsert_session("s1", started_at=1.0)
    injected = (
        "<command-message>okf:okf</command-message>\n"
        "<command-name>/okf:okf</command-name>\n"
        "<command-args>produce .okf</command-args>\n"
        "Base directory for this skill: /x\n\n" + "# corpo skill\n" * 200
    )
    rt = store.insert_event(
        session_id="s1", kind="round_trip", ts_start=2.0,
        payload={"request": {"body": {"messages": [
            {"role": "user", "content": [{"type": "text", "text": injected}]},
        ]}}, "response": {"message": {"content": []}}},
    )
    events = {e["id"]: e for e in store.get_session_events("s1")}
    assert events[rt]["input_snippet"] == "/okf:okf produce .okf"
    store.close()


def test_reassign_session_recomputes_turns_from_prompts(tmp_path):
    """Gli eventi fusi da una sessione sintetica ereditano il turno del
    UserPromptSubmit della sessione reale che li precede; quelli davvero
    pre-prompt restano a 0."""
    store = Store(str(tmp_path / "t.db"))
    store.upsert_session("real", started_at=1.0)
    store.upsert_session("syn-x", started_at=1.0)
    # round trip di servizio PRIMA di ogni prompt
    store.insert_event(session_id="syn-x", kind="round_trip", turn_index=0, ts_start=5.0)
    store.insert_event(
        session_id="real", kind="hook", subkind="UserPromptSubmit", turn_index=1, ts_start=10.0
    )
    # round trip del turno 1, arrivato quando la sessione era ancora sintetica
    store.insert_event(session_id="syn-x", kind="round_trip", turn_index=0, ts_start=11.0)
    store.insert_event(
        session_id="real", kind="hook", subkind="UserPromptSubmit", turn_index=2, ts_start=20.0
    )
    store.insert_event(session_id="syn-x", kind="round_trip", turn_index=0, ts_start=21.0)

    store.reassign_session("syn-x", "real")

    turns = {
        e["ts_start"]: e["turn_index"]
        for e in store.get_session_events("real")
        if e["kind"] == "round_trip"
    }
    assert turns == {5.0: 0, 11.0: 1, 21.0: 2}
    store.close()
