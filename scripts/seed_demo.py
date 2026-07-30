"""Populate a demo agentspy DB to try the UI without real traffic.

Creates three sessions: a live one with 4 turns, tool use, a subagent and an
MCP event; the subagent's child session; a short session already closed. The
payloads have the same shape as those produced by the proxy (request with
system/tools/messages + analysis, rebuilt SSE response), including
``<system-reminder>`` blocks in the user messages to exercise the detail
panel views.

Usage (from the server/ dir, the default DB is ./agentspy-demo.db):

    uv run python ../scripts/seed_demo.py
    AGENTSPY_DB=./agentspy-demo.db uv run agentspy
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from agentspy_server.providers.anthropic import analyze_request_body  # noqa: E402
from agentspy_server.store import Store  # noqa: E402

NOW = time.time()
DB = os.environ.get("AGENTSPY_DB", "./agentspy-demo.db")
if os.path.exists(DB):
    os.remove(DB)
store = Store(DB)

SYSTEM = (
    "You are Claude Code, Anthropic's official CLI for Claude. "
    "You are an interactive agent that helps users with software engineering tasks. "
    + "Lorem ipsum dolor sit amet. " * 200
)

TOOLS = [
    {"name": n, "description": f"Tool {n} description " + "x" * 400,
     "input_schema": {"type": "object", "properties": {"arg": {"type": "string"}}}}
    for n in ["Bash", "Read", "Write", "Edit", "Grep", "Glob", "Task", "WebFetch", "TodoWrite"]
]

REMINDER_1 = (
    "<system-reminder>\nAs you answer the user's questions, you can use the following context:\n"
    "# claudeMd\nCodebase and user instructions are shown below...\n" + "useful context. " * 120
    + "\n</system-reminder>"
)
REMINDER_2 = (
    "<system-reminder>The TodoWrite tool hasn't been used recently. "
    "Consider tracking progress if relevant.</system-reminder>"
)


def user_msg(prompt: str) -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": REMINDER_1},
            {"type": "text", "text": prompt + "\n\n" + REMINDER_2},
        ],
    }


# SKILL.md body injected by Claude Code when /okf:okf is invoked: it is real
# context cost, and it is what the new views (trigger badge + chip in the
# detail panel) highlight and measure.
SKILL_BODY = (
    "# Open Knowledge Format (OKF) skill\n\n"
    "OKF represents knowledge as a directory of markdown files with YAML "
    "frontmatter.\n\n## The one hard rule\n\nA bundle is conformant iff every "
    "non-reserved `.md` file has a parseable YAML frontmatter block with a "
    "non-empty `type` field.\n\n## Conventions\n\n" + "- one concept = one file. "
    "The file path (minus `.md`) is the concept ID.\n" * 30
)


def command_user_msg(name: str, args: str, body: str) -> dict:
    """User message as Claude Code composes it for a slash-command: the
    <command-*> wrapper followed by the injected SKILL.md, all in one text
    block (plus the usual context system-reminder)."""
    injected = (
        f"<command-message>{name}</command-message>\n"
        f"<command-name>/{name}</command-name>\n"
        f"<command-args>{args}</command-args>\n"
        f"Base directory for this skill: /home/sandro/.claude/plugins/okf\n\n"
        f"{body}\n\nARGUMENTS: {args}"
    )
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": REMINDER_1},
            {"type": "text", "text": injected},
        ],
    }


def rt_payload(model: str, messages: list, resp_blocks: list, usage: dict, stop: str,
               t0: float, dur: float, tag: str | None = None) -> dict:
    body = {"model": model, "max_tokens": 32000, "stream": True,
            "system": SYSTEM, "tools": TOOLS, "messages": messages}
    return {
        "method": "POST", "path": "/v1/messages", "query": None, "tag": tag,
        "timing": {"ts_start": t0, "ttfb_s": round(dur * 0.3, 3), "total_s": round(dur, 3)},
        "status": 200,
        "request": {"headers": {"x-api-key": "<redacted>"},
                    "analysis": analyze_request_body(body), "body": body},
        "response": {"type": "sse",
                     "message": {"id": "msg_x", "role": "assistant", "model": model,
                                 "content": resp_blocks},
                     "usage": usage, "stop_reason": stop,
                     "events_count": {"message_start": 1, "content_block_delta": 42}},
    }


def hook_payload(name: str, session_id: str, extra: dict | None = None) -> dict:
    p = {"hook_event_name": name, "session_id": session_id,
         "transcript_path": f"/home/sandro/.claude/projects/x/{session_id}.jsonl",
         "cwd": "/home/sandro/src/demo"}
    p.update(extra or {})
    return p


def add_rt(sid: str, turn: int, t0: float, model: str, messages: list, resp_blocks: list,
           usage: dict, tools_used: list[str], dur: float = 6.0, stop: str = "end_turn",
           cache_ttl: str = "1h") -> None:
    # TTL the tokens are cached with, as Claude Code picks it on real traffic:
    # 1h in main sessions, 5m in Task subagents. The tier lives in the usage
    # (`cache_creation`) and in the columns, because the two cost differently
    # (2x vs 1.25x the input).
    write = usage["cache_creation_input_tokens"]
    m5 = write if cache_ttl == "5m" else 0
    h1 = write if cache_ttl == "1h" else 0
    usage = {**usage, "cache_creation": {"ephemeral_5m_input_tokens": m5,
                                         "ephemeral_1h_input_tokens": h1}}
    store.insert_event(
        session_id=sid, kind="round_trip", subkind=None, turn_index=turn,
        ts_start=t0, ts_end=t0 + dur, ttfb_s=round(dur * 0.3, 3), model=model,
        status=200, stop_reason=stop,
        input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
        cache_read_tokens=usage["cache_read_input_tokens"],
        cache_write_tokens=write,
        cache_write_5m_tokens=m5, cache_write_1h_tokens=h1,
        tool_names=tools_used,
        payload=rt_payload(model, messages, resp_blocks, usage, stop, t0, dur),
    )


def add_hook(sid: str, name: str, turn: int, t0: float, extra: dict | None = None) -> None:
    store.insert_event(session_id=sid, kind="hook", subkind=name, turn_index=turn,
                       ts_start=t0, ts_end=t0, payload=hook_payload(name, sid, extra))


# ---------------------------------------------------------------- session A (live, featured)
A = "0a1b2c3d-1111-2222-3333-444455556666"
tA = NOW - 1500
store.upsert_session(A, tag="demo-live", title="Refactor authentication API", model="claude-fable-5",
                     started_at=tA, live=True)
add_hook(A, "SessionStart", 0, tA)

model_a = "claude-fable-5"
prompts = [
    "Analyze the authentication module and propose a refactor",
    "Apply the proposed refactor to the auth.py file",
    "Add tests for the new token flow",
    "Run the tests and fix the errors",
]
cache_read = 18000
t = tA + 5
msgs: list = []
for turn, prompt in enumerate(prompts, start=1):
    add_hook(A, "UserPromptSubmit", turn, t, {"prompt": prompt})
    t += 1
    msgs = msgs + [user_msg(prompt)]
    # 2-3 round trips per turn (tool use + final answer)
    n_rt = 3 if turn in (2, 4) else 2
    for i in range(n_rt):
        is_last = i == n_rt - 1
        cache_write = 2500 if i == 0 else 400
        inp = 150 + 80 * i
        out = 900 if not is_last else 450
        usage = {"input_tokens": inp, "output_tokens": out,
                 "cache_read_input_tokens": cache_read,
                 "cache_creation_input_tokens": cache_write}
        if not is_last:
            tool = ["Read", "Bash", "Edit", "Grep", "Write", "TodoWrite"][(turn + i) % 6]
            blocks = [
                {"type": "thinking", "thinking": "Thinking about what to do next..."},
                {"type": "text", "text": f"Going ahead with {tool} on the auth module."},
                {"type": "tool_use", "id": f"toolu_{turn}_{i}", "name": tool,
                 "input": {"arg": "auth.py"}},
            ]
            add_rt(A, turn, t, model_a, msgs, blocks, usage, [tool], stop="tool_use")
            add_hook(A, "PreToolUse", turn, t + 6.2, {"tool_name": tool})
            add_hook(A, "PostToolUse", turn, t + 7.0, {"tool_name": tool})
            msgs = msgs + [
                {"role": "assistant", "content": blocks},
                {"role": "user", "content": [{"type": "tool_result",
                                              "tool_use_id": f"toolu_{turn}_{i}",
                                              "content": "tool result " + "line\n" * 40}]},
            ]
        else:
            blocks = [{"type": "text",
                       "text": f"Done: completed the item '{prompt[:40]}...'. Technical summary."}]
            add_rt(A, turn, t, model_a, msgs, blocks, usage, [])
            msgs = msgs + [{"role": "assistant", "content": blocks}]
        cache_read += cache_write + inp + out
        t += 9
    # turn 3: subagent
    if turn == 3:
        agent_id = "agent-explore-42"
        SUB = f"sub-{agent_id}"
        add_hook(A, "SubagentStart", turn, t, {"agent_id": agent_id, "agent_type": "Explore"})
        store.upsert_session(SUB, title="Explore the test suite", model="claude-sonnet-5",
                             parent_session_id=A, agent_id=agent_id,
                             started_at=t, ended_at=t + 60, live=False)
        sub_cache = 9000
        st = t + 1
        smsgs: list = [user_msg("Explore the existing tests of the auth module")]
        for j in range(3):
            usage = {"input_tokens": 200, "output_tokens": 700,
                     "cache_read_input_tokens": sub_cache,
                     "cache_creation_input_tokens": 1200 if j == 0 else 300}
            blocks = [{"type": "text", "text": f"Step {j+1} of the exploration."}]
            if j < 2:
                blocks.append({"type": "tool_use", "id": f"toolu_s{j}", "name": "Grep",
                               "input": {"arg": "test_auth"}})
            add_rt(SUB, 1, st, "claude-sonnet-5", smsgs, blocks, usage,
                   ["Grep"] if j < 2 else [], stop="tool_use" if j < 2 else "end_turn",
                   cache_ttl="5m")
            sub_cache += 2000
            st += 8
        add_hook(A, "SubagentStop", turn, st, {"agent_id": agent_id})
        t = st + 2
    add_hook(A, "Stop", turn, t)
    t += 20

# turn 5: skill invocation via slash-command (/okf:okf) — exercises the
# "🎓 Command" trigger badge and the chip measuring the injected SKILL.md; the
# first round trip delegates to another skill with the Skill tool (🎓 badge in
# Tools).
add_hook(A, "UserPromptSubmit", 5, t, {"prompt": "/okf:okf produce .okf"})
t += 1
msgs = msgs + [command_user_msg("okf:okf", "produce .okf", SKILL_BODY)]
skill_usage = {"input_tokens": 320, "output_tokens": 600,
               "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": 2200}
skill_blocks = [
    {"type": "text", "text": "To produce the bundle I lean on the documents skill."},
    {"type": "tool_use", "id": "toolu_5_0", "name": "Skill",
     "input": {"skill": "document-skills:pdf", "args": "extract structure"}},
]
add_rt(A, 5, t, model_a, msgs, skill_blocks, skill_usage, ["Skill"], stop="tool_use")
add_hook(A, "PreToolUse", 5, t + 6.2, {"tool_name": "Skill", "tool_input": {"skill": "document-skills:pdf"}})
msgs = msgs + [
    {"role": "assistant", "content": skill_blocks},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_5_0",
                                  "content": "skill document-skills:pdf loaded"}]},
]
t += 9
final5 = [{"type": "text", "text": "OKF bundle produced in .okf/ and validated."}]
add_rt(A, 5, t, model_a, msgs, final5,
       {"input_tokens": 260, "output_tokens": 380,
        "cache_read_input_tokens": cache_read + 3000, "cache_creation_input_tokens": 300}, [])
msgs = msgs + [{"role": "assistant", "content": final5}]
add_hook(A, "Stop", 5, t + 6)

# MCP event in session A
store.insert_event(
    session_id=A, kind="mcp", subkind="context7:query-docs", turn_index=2,
    ts_start=tA + 120, ts_end=tA + 121.5,
    payload={"server_name": "context7", "method": "query-docs", "rpc_id": 42,
             "kind": "call", "direction": "client->server",
             "params": {"query": "starlette websocket"},
             "result": {"content": [{"type": "text", "text": "starlette WebSocket docs…"}]}},
)

# ---------------------------------------------------------------- session B (closed, short)
B = "0b2c3d4e-7777-8888-9999-aaaabbbbcccc"
tB = NOW - 5400
store.upsert_session(B, tag="demo-short", title="Fix typo in the README", model="claude-sonnet-5",
                     started_at=tB, ended_at=tB + 90, live=False)
add_hook(B, "SessionStart", 0, tB)
add_hook(B, "UserPromptSubmit", 1, tB + 2, {"prompt": "Fix the typos in the README"})
bmsgs = [user_msg("Fix the typos in the README")]
bc = 12000
for i in range(2):
    usage = {"input_tokens": 120, "output_tokens": 500,
             "cache_read_input_tokens": bc, "cache_creation_input_tokens": 800 if i == 0 else 100}
    blocks = ([{"type": "tool_use", "id": f"toolu_b{i}", "name": "Edit", "input": {"arg": "README.md"}}]
              if i == 0 else [{"type": "text", "text": "Typos fixed."}])
    add_rt(B, 1, tB + 4 + i * 10, "claude-sonnet-5", bmsgs, blocks, usage,
           ["Edit"] if i == 0 else [], stop="tool_use" if i == 0 else "end_turn")
    bc += 1000
add_hook(B, "Stop", 1, tB + 30)

store.close()
sessions = Store(DB).get_sessions()
print(f"DB {DB}: {len(sessions)} sessions")
for s in sessions:
    print(" -", s["id"][:16], s.get("title"), "live" if s.get("live") else "closed",
          "rt:", s.get("round_trips"))
