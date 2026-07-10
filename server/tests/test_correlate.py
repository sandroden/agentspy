from agentspy_server.correlate import Correlator


def test_fingerprint_chains_synthetic_round_trips():
    """Tre round trip della stessa conversazione (nessun hook): stesso fingerprint
    -> stessa sessione sintetica; il turno avanza solo su nuovo testo utente non
    tool_result."""
    correlator = Correlator()

    record1 = {
        "tag": "run-A",
        "request": {"body": {"system": "sys", "messages": [{"role": "user", "content": "Ciao"}]}},
        "response": {"message": {"content": []}},
    }
    info1 = correlator.correlate_round_trip(record1)
    assert info1["is_new_session"] is True
    assert info1["is_new_turn"] is True
    assert info1["turn_index"] == 1
    assert info1["session_id"].startswith("syn-")

    record2 = {
        "request": {
            "body": {
                "system": "sys",
                "messages": [
                    {"role": "user", "content": "Ciao"},
                    {"role": "assistant", "content": [{"type": "text", "text": "Ciao a te"}]},
                    {"role": "user", "content": "Come stai?"},
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    info2 = correlator.correlate_round_trip(record2)
    assert info2["session_id"] == info1["session_id"]
    assert info2["is_new_turn"] is True
    assert info2["turn_index"] == 2

    record3 = {
        "request": {
            "body": {
                "system": "sys",
                "messages": [
                    {"role": "user", "content": "Ciao"},
                    {"role": "assistant", "content": [{"type": "text", "text": "Ciao a te"}]},
                    {"role": "user", "content": "Come stai?"},
                    {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash"}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}
                        ],
                    },
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    info3 = correlator.correlate_round_trip(record3)
    assert info3["session_id"] == info1["session_id"]
    assert info3["is_new_turn"] is False
    assert info3["turn_index"] == 2

    # il tag mandato nel primo round trip resta sulla sessione
    assert correlator.session_state[info1["session_id"]].tag == "run-A"


def test_user_prompt_submit_advances_turn():
    correlator = Correlator()
    info1 = correlator.correlate_hook(
        {"session_id": "real-1", "hook_event_name": "UserPromptSubmit", "prompt": "fai una cosa"}
    )
    assert info1["turn_index"] == 1
    assert info1["is_new_turn"] is True

    info2 = correlator.correlate_hook(
        {"session_id": "real-1", "hook_event_name": "UserPromptSubmit", "prompt": "fai un'altra cosa"}
    )
    assert info2["turn_index"] == 2


def test_pretooluse_merges_synthetic_session_into_real_one():
    correlator = Correlator()

    record = {
        "request": {"body": {"system": "sys", "messages": [{"role": "user", "content": "ciao"}]}},
        "response": {"message": {"content": [{"type": "tool_use", "id": "toolu_42", "name": "Bash"}]}},
    }
    info = correlator.correlate_round_trip(record)
    synthetic_id = info["session_id"]
    assert synthetic_id.startswith("syn-")

    hook_info = correlator.correlate_hook(
        {"session_id": "real-session-1", "hook_event_name": "PreToolUse", "tool_use_id": "toolu_42"}
    )
    assert hook_info["session_id"] == "real-session-1"

    # un round trip successivo della stessa conversazione ora mappa alla sessione reale
    record2 = {
        "request": {
            "body": {
                "system": "sys",
                "messages": [
                    {"role": "user", "content": "ciao"},
                    {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "id": "toolu_42", "name": "Bash"}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": "toolu_42", "content": "ok"}
                        ],
                    },
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    info2 = correlator.correlate_round_trip(record2)
    assert info2["session_id"] == "real-session-1"


def test_subagent_hooks_route_to_child_session():
    """Schema reale (verificato su Claude Code): gli hook del subagente portano
    agent_id + session_id della MADRE. SubagentStart/Stop restano marker sulla
    madre; i tool hook del subagente vanno nella sessione figlia sub-<agent_id>;
    la conversazione API del subagente si aggancia alla figlia via tool_use_id."""
    correlator = Correlator()

    # SubagentStart: evento sulla madre + sessione figlia dichiarata
    start_info = correlator.correlate_hook(
        {
            "session_id": "mother-1",
            "hook_event_name": "SubagentStart",
            "agent_id": "ag123",
            "agent_type": "Explore",
        }
    )
    assert start_info["session_id"] == "mother-1"  # marker sulla madre
    assert start_info["child_session"] == {
        "id": "sub-ag123",
        "agent_id": "ag123",
        "agent_type": "Explore",
        "parent_session_id": "mother-1",
    }
    assert start_info["child_ended"] is False
    # la madre NON deve ereditare l'agent_id del figlio
    assert correlator.session_state["mother-1"].agent_id is None

    # round trip della conversazione del subagente (fingerprint proprio)
    sub_record = {
        "request": {"body": {"system": "sys-sub", "messages": [{"role": "user", "content": "conta"}]}},
        "response": {"message": {"content": [{"type": "tool_use", "id": "toolu_glob", "name": "Glob"}]}},
    }
    synthetic_id = correlator.correlate_round_trip(sub_record)["session_id"]
    assert synthetic_id.startswith("syn-")

    # PreToolUse del tool del subagente: agent_id valorizzato, session della madre
    pre_info = correlator.correlate_hook(
        {
            "session_id": "mother-1",
            "hook_event_name": "PreToolUse",
            "agent_id": "ag123",
            "tool_name": "Glob",
            "tool_use_id": "toolu_glob",
        }
    )
    assert pre_info["session_id"] == "sub-ag123"  # l'evento va nella figlia
    assert pre_info["merged_from"] == [synthetic_id]  # la conversazione pure
    assert pre_info["parent_session_id"] == "mother-1"

    # round trip successivo del subagente -> direttamente nella figlia
    sub_record2 = {
        "request": {
            "body": {
                "system": "sys-sub",
                "messages": [
                    {"role": "user", "content": "conta"},
                    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_glob", "name": "Glob"}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_glob", "content": "3"}]},
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    assert correlator.correlate_round_trip(sub_record2)["session_id"] == "sub-ag123"

    # SubagentStop: marker sulla madre, figlia dichiarata chiusa
    stop_info = correlator.correlate_hook(
        {
            "session_id": "mother-1",
            "hook_event_name": "SubagentStop",
            "agent_id": "ag123",
            "agent_type": "Explore",
        }
    )
    assert stop_info["session_id"] == "mother-1"
    assert stop_info["child_ended"] is True


def test_prompt_binding_links_toolless_conversation():
    """Una conversazione senza tool call (nessun tool_use_id da joinare) si
    aggancia alla sessione reale confrontando l'ultimo messaggio user con il
    prompt annunciato da UserPromptSubmit."""
    correlator = Correlator()
    correlator.correlate_hook(
        {"session_id": "real-lesson", "hook_event_name": "UserPromptSubmit", "prompt": "Estrai le lezioni."}
    )
    record = {
        "request": {
            "body": {
                "system": "sys-lesson",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "<system-reminder>bla</system-reminder>"},
                            {"type": "text", "text": "Estrai le lezioni."},
                        ],
                    }
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    info = correlator.correlate_round_trip(record)
    assert info["session_id"] == "real-lesson"
    assert info["is_new_session"] is False
    # il turno resta quello della sessione reale (da hook), niente doppio conteggio
    assert info["turn_index"] == 1


def test_fingerprint_ignores_cache_control_markers():
    """I marker cache_control si spostano fra un round trip e il successivo
    (il checkpoint di cache avanza): non devono spezzare la sessione."""
    correlator = Correlator()

    record1 = {
        "request": {
            "body": {
                "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "ciao", "cache_control": {"type": "ephemeral"}}
                        ],
                    }
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    record2 = {
        "request": {
            "body": {
                "system": [{"type": "text", "text": "sys"}],  # marker spostato altrove
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "ciao"}]},
                    {"role": "assistant", "content": [{"type": "text", "text": "ehi"}]},
                    {"role": "user", "content": "come va?"},
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    info1 = correlator.correlate_round_trip(record1)
    info2 = correlator.correlate_round_trip(record2)
    assert info2["session_id"] == info1["session_id"]
    assert info2["is_new_session"] is False


def test_merge_reports_merged_from():
    """Quando PreToolUse identifica una sessione sintetica con quella reale,
    correlate_hook deve segnalare l'id assorbito perché il chiamante possa
    riassegnare gli eventi nello store."""
    correlator = Correlator()
    record = {
        "request": {"body": {"system": "s", "messages": [{"role": "user", "content": "x"}]}},
        "response": {"message": {"content": [{"type": "tool_use", "id": "toolu_m", "name": "Read"}]}},
    }
    synthetic_id = correlator.correlate_round_trip(record)["session_id"]

    hook_info = correlator.correlate_hook(
        {"session_id": "real-9", "hook_event_name": "PreToolUse", "tool_use_id": "toolu_m"}
    )
    assert hook_info["merged_from"] == [synthetic_id]

    # un secondo PreToolUse sulla stessa sessione non deve rifondere nulla
    hook_info2 = correlator.correlate_hook(
        {"session_id": "real-9", "hook_event_name": "PreToolUse", "tool_use_id": "toolu_m"}
    )
    assert hook_info2["merged_from"] == []


def test_tag_from_header_on_round_trip():
    correlator = Correlator()
    record = {
        "tag": "notte-1",
        "request": {"body": {"system": "sys", "messages": [{"role": "user", "content": "ciao"}]}},
        "response": {"message": {"content": []}},
    }
    info = correlator.correlate_round_trip(record)
    assert correlator.session_state[info["session_id"]].tag == "notte-1"


def test_header_session_id_parents_synthetic_session():
    """Un round trip con header x-claude-code-session-id di una sessione già
    nota via hook: la sintetica viene nidificata sotto la madre (non fusa,
    perché potrebbe essere la conversazione di un subagente)."""
    correlator = Correlator()
    correlator.correlate_hook({"session_id": "real-9", "hook_event_name": "SessionStart"})

    record = {
        "request": {
            "headers": {"x-claude-code-session-id": "real-9"},
            "body": {"system": "svc", "messages": [{"role": "user", "content": "quota?"}]},
        },
        "response": {"message": {"content": []}},
    }
    info = correlator.correlate_round_trip(record)
    assert info["session_id"].startswith("syn-")
    assert info["parent_session_id"] == "real-9"


def test_header_session_id_ignored_when_mother_unknown():
    """Se la madre non è mai stata vista via hook (progetto senza hook o
    collector riavviato) la sintetica resta top-level: un parent che non
    esiste come riga la farebbe sparire dalla sidebar."""
    correlator = Correlator()

    record = {
        "request": {
            "headers": {"x-claude-code-session-id": "mai-vista"},
            "body": {"system": "svc", "messages": [{"role": "user", "content": "quota?"}]},
        },
        "response": {"message": {"content": []}},
    }
    info = correlator.correlate_round_trip(record)
    assert info["session_id"].startswith("syn-")
    assert info["parent_session_id"] is None


def _rt(session_key, system, prompt, *, tool_use_id=None, tag=None):
    """Round trip minimale con header x-claude-code-session-id e un solo prompt."""
    response_content = (
        [{"type": "tool_use", "id": tool_use_id, "name": "Bash"}] if tool_use_id else []
    )
    return {
        "tag": tag,
        "request": {
            "headers": {"x-claude-code-session-id": session_key},
            "body": {"system": system, "messages": [{"role": "user", "content": prompt}]},
        },
        "response": {"message": {"content": response_content}},
    }


def test_concurrent_runs_same_prompt_stay_distinct():
    """Due run concorrenti con lo STESSO system e lo STESSO primo prompt ma
    session_id (header) diversi devono restare due sessioni distinte, mai
    collassare in una: il session_key entra nel fingerprint."""
    correlator = Correlator()

    a1 = correlator.correlate_round_trip(_rt("sess-A", "sys", "Ciao", tag="run-A"))
    b1 = correlator.correlate_round_trip(_rt("sess-B", "sys", "Ciao", tag="run-B"))
    assert a1["session_id"] != b1["session_id"]
    assert a1["session_id"].startswith("syn-") and b1["session_id"].startswith("syn-")

    # round trip successivi della stessa conversazione restano nella propria
    a2 = correlator.correlate_round_trip(_rt("sess-A", "sys", "Ciao"))
    b2 = correlator.correlate_round_trip(_rt("sess-B", "sys", "Ciao"))
    assert a2["session_id"] == a1["session_id"]
    assert b2["session_id"] == b1["session_id"]


def test_concurrent_runs_same_prompt_bind_to_correct_hook_session():
    """Due run con lo stesso prompt annunciato da UserPromptSubmit su session_id
    hook diversi: il binding via prompt NON deve collassarle, e ciascun round
    trip deve legarsi alla PROPRIA sessione hook grazie al session_key."""
    correlator = Correlator()
    correlator.correlate_hook(
        {"session_id": "sess-A", "hook_event_name": "UserPromptSubmit", "prompt": "fai la cosa"}
    )
    correlator.correlate_hook(
        {"session_id": "sess-B", "hook_event_name": "UserPromptSubmit", "prompt": "fai la cosa"}
    )

    info_a = correlator.correlate_round_trip(_rt("sess-A", "sysA", "fai la cosa"))
    info_b = correlator.correlate_round_trip(_rt("sess-B", "sysB", "fai la cosa"))

    assert info_a["session_id"] == "sess-A"
    assert info_b["session_id"] == "sess-B"
    assert info_a["session_id"] != info_b["session_id"]


def test_rehydrate_continues_session_and_turn(tmp_path):
    """Store popolato → nuovo Correlator reidratato: turn_index, fingerprint e
    join per tool_use_id tornano, e il round trip successivo continua la stessa
    sessione col suo turno invece di ripartire da 1 in una nuova syn-."""
    from agentspy_server.store import Store

    store = Store(tmp_path / "rehy.db")
    store.upsert_session("sess-R", started_at=100.0, ended_at=101.0, live=True)
    store.insert_event(
        session_id="sess-R", kind="hook", subkind="UserPromptSubmit",
        turn_index=1, ts_start=100.0, ts_end=100.0,
        payload={"session_id": "sess-R", "hook_event_name": "UserPromptSubmit", "prompt": "ciao"},
    )
    rt_payload = {
        "request": {
            "headers": {"x-claude-code-session-id": "sess-R"},
            "body": {"system": "sys", "messages": [{"role": "user", "content": "ciao"}]},
        },
        "response": {"message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash"}]}},
    }
    store.insert_event(
        session_id="sess-R", kind="round_trip", turn_index=1,
        ts_start=100.5, ts_end=101.0, payload=rt_payload,
    )

    snap = store.rehydration_snapshot(0.0)
    corr = Correlator()
    corr.rehydrate(snap["sessions"], snap["events"])

    assert corr.session_state["sess-R"].turn_index == 1
    assert corr.session_state["sess-R"].has_hooks is True
    # join MCP/subagente ripristinato: il tool_use della risposta è ricollegato
    assert corr.session_for_tool_use("toolu_1") == "sess-R"

    # round trip successivo della stessa conversazione: continua sess-R al turno 1
    next_rt = {
        "request": {
            "headers": {"x-claude-code-session-id": "sess-R"},
            "body": {
                "system": "sys",
                "messages": [
                    {"role": "user", "content": "ciao"},
                    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash"}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}]},
                ],
            },
        },
        "response": {"message": {"content": []}},
    }
    info = corr.correlate_round_trip(next_rt)
    assert info["session_id"] == "sess-R"
    assert info["turn_index"] == 1
    assert info["is_new_session"] is False
    store.close()


def test_rehydration_snapshot_filters_by_recency(tmp_path):
    """Lo snapshot prende le sessioni per recency (ultima attività) e tutti i
    loro eventi; le sessioni vecchie sono escluse."""
    from agentspy_server.store import Store

    store = Store(tmp_path / "rehy2.db")
    store.upsert_session("old", started_at=10.0, ended_at=10.0, live=False)
    store.upsert_session("new", started_at=1000.0, ended_at=1000.0, live=True)
    store.insert_event(session_id="old", kind="hook", subkind="SessionStart", ts_start=10.0)
    store.insert_event(session_id="new", kind="hook", subkind="SessionStart", ts_start=1000.0)

    snap = store.rehydration_snapshot(500.0)
    assert {s["id"] for s in snap["sessions"]} == {"new"}
    assert all(e["session_id"] == "new" for e in snap["events"])
    store.close()


def test_prompt_binding_survives_trailing_system_message():
    """Claude Code (cli >= 2.1) accoda un messaggio role='system' dopo il
    prompt utente: il binding via prompt e il turno devono basarsi sull'ultimo
    messaggio USER, non su messages[-1] (bug: round trip in 'pre-prompt')."""
    correlator = Correlator()
    correlator.correlate_hook({"session_id": "real-7", "hook_event_name": "SessionStart"})
    correlator.correlate_hook(
        {"session_id": "real-7", "hook_event_name": "UserPromptSubmit", "prompt": "che ore sono?"}
    )

    record = {
        "request": {
            "body": {
                "system": "sys",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "<system-reminder>contesto</system-reminder>"},
                            {"type": "text", "text": "che ore sono?"},
                        ],
                    },
                    {"role": "system", "content": "The following deferred tools..."},
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    info = correlator.correlate_round_trip(record)
    assert info["session_id"] == "real-7"
    assert info["turn_index"] == 1
