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
