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


def test_subagent_binding_via_subagent_start():
    correlator = Correlator()

    parent_record = {
        "request": {
            "body": {"system": "sys-parent", "messages": [{"role": "user", "content": "esegui subagente"}]}
        },
        "response": {"message": {"content": [{"type": "tool_use", "id": "toolu_task_1", "name": "Task"}]}},
    }
    parent_info = correlator.correlate_round_trip(parent_record)
    parent_session_id = parent_info["session_id"]

    sub_info = correlator.correlate_hook(
        {
            "session_id": "child-session-1",
            "hook_event_name": "SubagentStart",
            "agent_id": "explorer",
            "parent_tool_use_id": "toolu_task_1",
        }
    )
    assert sub_info["parent_session_id"] == parent_session_id
    assert sub_info["agent_id"] == "explorer"


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
