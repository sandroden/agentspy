from agentspy_server.correlate import Correlator


def test_fingerprint_chains_synthetic_round_trips():
    """Three round trips of the same conversation (no hooks): same fingerprint
    -> same synthetic session; the turn advances only on new user text that is
    not a tool_result."""
    correlator = Correlator()

    record1 = {
        "tag": "run-A",
        "request": {"body": {"system": "sys", "messages": [{"role": "user", "content": "Hi"}]}},
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
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": [{"type": "text", "text": "Hi there"}]},
                    {"role": "user", "content": "How are you?"},
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
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": [{"type": "text", "text": "Hi there"}]},
                    {"role": "user", "content": "How are you?"},
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

    # the tag sent in the first round trip stays on the session
    assert correlator.session_state[info1["session_id"]].tag == "run-A"


def test_user_prompt_submit_advances_turn():
    correlator = Correlator()
    info1 = correlator.correlate_hook(
        {"session_id": "real-1", "hook_event_name": "UserPromptSubmit", "prompt": "do a thing"}
    )
    assert info1["turn_index"] == 1
    assert info1["is_new_turn"] is True

    info2 = correlator.correlate_hook(
        {"session_id": "real-1", "hook_event_name": "UserPromptSubmit", "prompt": "do another thing"}
    )
    assert info2["turn_index"] == 2


def test_pretooluse_merges_synthetic_session_into_real_one():
    correlator = Correlator()

    record = {
        "request": {"body": {"system": "sys", "messages": [{"role": "user", "content": "hi"}]}},
        "response": {"message": {"content": [{"type": "tool_use", "id": "toolu_42", "name": "Bash"}]}},
    }
    info = correlator.correlate_round_trip(record)
    synthetic_id = info["session_id"]
    assert synthetic_id.startswith("syn-")

    hook_info = correlator.correlate_hook(
        {"session_id": "real-session-1", "hook_event_name": "PreToolUse", "tool_use_id": "toolu_42"}
    )
    assert hook_info["session_id"] == "real-session-1"

    # a later round trip of the same conversation now maps to the real session
    record2 = {
        "request": {
            "body": {
                "system": "sys",
                "messages": [
                    {"role": "user", "content": "hi"},
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
    """Real scheme (verified on Claude Code): subagent hooks carry the agent_id
    + the session_id of the PARENT. SubagentStart/Stop stay markers on the
    parent; the subagent tool hooks go into the child session sub-<agent_id>;
    the subagent API conversation binds to the child via tool_use_id."""
    correlator = Correlator()

    # SubagentStart: event on the parent + declared child session
    start_info = correlator.correlate_hook(
        {
            "session_id": "mother-1",
            "hook_event_name": "SubagentStart",
            "agent_id": "ag123",
            "agent_type": "Explore",
        }
    )
    assert start_info["session_id"] == "mother-1"  # marker on the parent
    assert start_info["child_session"] == {
        "id": "sub-ag123",
        "agent_id": "ag123",
        "agent_type": "Explore",
        "parent_session_id": "mother-1",
    }
    assert start_info["child_ended"] is False
    # the parent must NOT inherit the child's agent_id
    assert correlator.session_state["mother-1"].agent_id is None

    # round trip of the subagent conversation (its own fingerprint)
    sub_record = {
        "request": {"body": {"system": "sys-sub", "messages": [{"role": "user", "content": "count"}]}},
        "response": {"message": {"content": [{"type": "tool_use", "id": "toolu_glob", "name": "Glob"}]}},
    }
    synthetic_id = correlator.correlate_round_trip(sub_record)["session_id"]
    assert synthetic_id.startswith("syn-")

    # PreToolUse of the subagent tool: agent_id set, session of the parent
    pre_info = correlator.correlate_hook(
        {
            "session_id": "mother-1",
            "hook_event_name": "PreToolUse",
            "agent_id": "ag123",
            "tool_name": "Glob",
            "tool_use_id": "toolu_glob",
        }
    )
    assert pre_info["session_id"] == "sub-ag123"  # the event goes into the child
    assert pre_info["merged_from"] == [synthetic_id]  # so does the conversation
    assert pre_info["parent_session_id"] == "mother-1"

    # later round trip of the subagent -> straight into the child
    sub_record2 = {
        "request": {
            "body": {
                "system": "sys-sub",
                "messages": [
                    {"role": "user", "content": "count"},
                    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_glob", "name": "Glob"}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_glob", "content": "3"}]},
                ],
            }
        },
        "response": {"message": {"content": []}},
    }
    assert correlator.correlate_round_trip(sub_record2)["session_id"] == "sub-ag123"

    # SubagentStop: marker on the parent, child declared closed
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
    """A conversation without tool calls (no tool_use_id to join on) binds to
    the real session by comparing the last user message with the prompt
    announced by UserPromptSubmit."""
    correlator = Correlator()
    correlator.correlate_hook(
        {"session_id": "real-lesson", "hook_event_name": "UserPromptSubmit", "prompt": "Extract the lessons."}
    )
    record = {
        "request": {
            "body": {
                "system": "sys-lesson",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "<system-reminder>blah</system-reminder>"},
                            {"type": "text", "text": "Extract the lessons."},
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
    # the turn stays the one of the real session (from hooks), no double count
    assert info["turn_index"] == 1


def test_fingerprint_ignores_cache_control_markers():
    """The cache_control markers move between one round trip and the next (the
    cache checkpoint advances): they must not break the session apart."""
    correlator = Correlator()

    record1 = {
        "request": {
            "body": {
                "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}
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
                "system": [{"type": "text", "text": "sys"}],  # marker moved elsewhere
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "hi"}]},
                    {"role": "assistant", "content": [{"type": "text", "text": "hey"}]},
                    {"role": "user", "content": "how's it going?"},
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
    """When PreToolUse identifies a synthetic session with the real one,
    correlate_hook must report the absorbed id so that the caller can reassign
    the events in the store."""
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

    # a second PreToolUse on the same session must not merge anything again
    hook_info2 = correlator.correlate_hook(
        {"session_id": "real-9", "hook_event_name": "PreToolUse", "tool_use_id": "toolu_m"}
    )
    assert hook_info2["merged_from"] == []


def test_tag_from_header_on_round_trip():
    correlator = Correlator()
    record = {
        "tag": "night-1",
        "request": {"body": {"system": "sys", "messages": [{"role": "user", "content": "hi"}]}},
        "response": {"message": {"content": []}},
    }
    info = correlator.correlate_round_trip(record)
    assert correlator.session_state[info["session_id"]].tag == "night-1"


def test_header_session_id_parents_synthetic_session():
    """A round trip with the x-claude-code-session-id header of a session
    already known via hooks: the synthetic one is nested under the parent (not
    merged, because it could be a subagent conversation)."""
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
    """If the parent was never seen via hooks (project without hooks or
    collector restarted) the synthetic one stays top-level: a parent that does
    not exist as a row would make it disappear from the sidebar."""
    correlator = Correlator()

    record = {
        "request": {
            "headers": {"x-claude-code-session-id": "never-seen"},
            "body": {"system": "svc", "messages": [{"role": "user", "content": "quota?"}]},
        },
        "response": {"message": {"content": []}},
    }
    info = correlator.correlate_round_trip(record)
    assert info["session_id"].startswith("syn-")
    assert info["parent_session_id"] is None


def _rt(session_key, system, prompt, *, tool_use_id=None, tag=None):
    """Minimal round trip with the x-claude-code-session-id header and a single prompt."""
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
    """Two concurrent runs with the SAME system and the SAME first prompt but
    different session_id (header) must stay two distinct sessions, never
    collapse into one: the session_key enters the fingerprint."""
    correlator = Correlator()

    a1 = correlator.correlate_round_trip(_rt("sess-A", "sys", "Hi", tag="run-A"))
    b1 = correlator.correlate_round_trip(_rt("sess-B", "sys", "Hi", tag="run-B"))
    assert a1["session_id"] != b1["session_id"]
    assert a1["session_id"].startswith("syn-") and b1["session_id"].startswith("syn-")

    # later round trips of the same conversation stay in their own session
    a2 = correlator.correlate_round_trip(_rt("sess-A", "sys", "Hi"))
    b2 = correlator.correlate_round_trip(_rt("sess-B", "sys", "Hi"))
    assert a2["session_id"] == a1["session_id"]
    assert b2["session_id"] == b1["session_id"]


def test_concurrent_runs_same_prompt_bind_to_correct_hook_session():
    """Two runs with the same prompt announced by UserPromptSubmit on different
    hook session_id: binding via prompt must NOT collapse them, and each round
    trip must bind to its OWN hook session thanks to the session_key."""
    correlator = Correlator()
    correlator.correlate_hook(
        {"session_id": "sess-A", "hook_event_name": "UserPromptSubmit", "prompt": "do the thing"}
    )
    correlator.correlate_hook(
        {"session_id": "sess-B", "hook_event_name": "UserPromptSubmit", "prompt": "do the thing"}
    )

    info_a = correlator.correlate_round_trip(_rt("sess-A", "sysA", "do the thing"))
    info_b = correlator.correlate_round_trip(_rt("sess-B", "sysB", "do the thing"))

    assert info_a["session_id"] == "sess-A"
    assert info_b["session_id"] == "sess-B"
    assert info_a["session_id"] != info_b["session_id"]


def test_rehydrate_continues_session_and_turn(tmp_path):
    """Populated store → new rehydrated Correlator: turn_index, fingerprint and
    the tool_use_id join come back, and the next round trip continues the same
    session with its turn instead of restarting from 1 in a new syn-."""
    from agentspy_server.store import Store

    store = Store(tmp_path / "rehy.db")
    store.upsert_session("sess-R", started_at=100.0, ended_at=101.0, live=True)
    store.insert_event(
        session_id="sess-R", kind="hook", subkind="UserPromptSubmit",
        turn_index=1, ts_start=100.0, ts_end=100.0,
        payload={"session_id": "sess-R", "hook_event_name": "UserPromptSubmit", "prompt": "hi"},
    )
    rt_payload = {
        "request": {
            "headers": {"x-claude-code-session-id": "sess-R"},
            "body": {"system": "sys", "messages": [{"role": "user", "content": "hi"}]},
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
    # MCP/subagent join restored: the tool_use of the response is relinked
    assert corr.session_for_tool_use("toolu_1") == "sess-R"

    # next round trip of the same conversation: continues sess-R at turn 1
    next_rt = {
        "request": {
            "headers": {"x-claude-code-session-id": "sess-R"},
            "body": {
                "system": "sys",
                "messages": [
                    {"role": "user", "content": "hi"},
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
    """The snapshot takes sessions by recency (last activity) and all of their
    events; old sessions are excluded."""
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
    """Claude Code (cli >= 2.1) appends a role='system' message after the user
    prompt: binding via prompt and the turn must rely on the last USER message,
    not on messages[-1] (bug: round trip stuck in 'pre-prompt')."""
    correlator = Correlator()
    correlator.correlate_hook({"session_id": "real-7", "hook_event_name": "SessionStart"})
    correlator.correlate_hook(
        {"session_id": "real-7", "hook_event_name": "UserPromptSubmit", "prompt": "what time is it?"}
    )

    record = {
        "request": {
            "body": {
                "system": "sys",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "<system-reminder>context</system-reminder>"},
                            {"type": "text", "text": "what time is it?"},
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
