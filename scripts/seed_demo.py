"""Popola un DB agentspy dimostrativo per provare la UI senza traffico reale.

Crea tre sessioni: una live con 4 turni, tool use, un subagente e un evento
MCP; la sessione figlia del subagente; una sessione breve già chiusa. I
payload hanno la stessa forma di quelli prodotti dal proxy (request con
system/tools/messages + analysis, response SSE ricostruita), inclusi blocchi
``<system-reminder>`` nei messaggi user per esercitare le viste del pannello
di dettaglio.

Uso (dalla dir server/, il DB di default è ./agentspy-demo.db):

    uv run python ../scripts/seed_demo.py
    AGENTSPY_DB=./agentspy-demo.db uv run agentspy
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from agentspy_server.proxy import analyze_request_body  # noqa: E402
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
    "# claudeMd\nCodebase and user instructions are shown below...\n" + "contesto utile. " * 120
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
           usage: dict, tools_used: list[str], dur: float = 6.0, stop: str = "end_turn") -> None:
    store.insert_event(
        session_id=sid, kind="round_trip", subkind=None, turn_index=turn,
        ts_start=t0, ts_end=t0 + dur, ttfb_s=round(dur * 0.3, 3), model=model,
        status=200, stop_reason=stop,
        input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
        cache_read_tokens=usage["cache_read_input_tokens"],
        cache_write_tokens=usage["cache_creation_input_tokens"],
        tool_names=tools_used,
        payload=rt_payload(model, messages, resp_blocks, usage, stop, t0, dur),
    )


def add_hook(sid: str, name: str, turn: int, t0: float, extra: dict | None = None) -> None:
    store.insert_event(session_id=sid, kind="hook", subkind=name, turn_index=turn,
                       ts_start=t0, ts_end=t0, payload=hook_payload(name, sid, extra))


# ---------------------------------------------------------------- sessione A (live, featured)
A = "0a1b2c3d-1111-2222-3333-444455556666"
tA = NOW - 1500
store.upsert_session(A, tag="demo-live", title="Refactor API autenticazione", model="claude-fable-5",
                     started_at=tA, live=True)
add_hook(A, "SessionStart", 0, tA)

model_a = "claude-fable-5"
prompts = [
    "Analizza il modulo di autenticazione e proponi un refactor",
    "Applica il refactor proposto al file auth.py",
    "Aggiungi i test per il nuovo flusso token",
    "Lancia i test e sistema gli errori",
]
cache_read = 18000
t = tA + 5
msgs: list = []
for turn, prompt in enumerate(prompts, start=1):
    add_hook(A, "UserPromptSubmit", turn, t, {"prompt": prompt})
    t += 1
    msgs = msgs + [user_msg(prompt)]
    # 2-3 round trip per turno (uso tool + risposta finale)
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
                {"type": "thinking", "thinking": "Ragiono sul da farsi..."},
                {"type": "text", "text": f"Procedo con {tool} sul modulo auth."},
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
                                              "content": "risultato del tool " + "riga\n" * 40}]},
            ]
        else:
            blocks = [{"type": "text",
                       "text": f"Fatto: completato il punto '{prompt[:40]}...'. Riepilogo tecnico."}]
            add_rt(A, turn, t, model_a, msgs, blocks, usage, [])
            msgs = msgs + [{"role": "assistant", "content": blocks}]
        cache_read += cache_write + inp + out
        t += 9
    # turno 3: subagente
    if turn == 3:
        agent_id = "agent-explore-42"
        SUB = f"sub-{agent_id}"
        add_hook(A, "SubagentStart", turn, t, {"agent_id": agent_id, "agent_type": "Explore"})
        store.upsert_session(SUB, title="Explora suite di test", model="claude-sonnet-5",
                             parent_session_id=A, agent_id=agent_id,
                             started_at=t, ended_at=t + 60, live=False)
        sub_cache = 9000
        st = t + 1
        smsgs: list = [user_msg("Esplora i test esistenti del modulo auth")]
        for j in range(3):
            usage = {"input_tokens": 200, "output_tokens": 700,
                     "cache_read_input_tokens": sub_cache,
                     "cache_creation_input_tokens": 1200 if j == 0 else 300}
            blocks = [{"type": "text", "text": f"Passo {j+1} dell'esplorazione."}]
            if j < 2:
                blocks.append({"type": "tool_use", "id": f"toolu_s{j}", "name": "Grep",
                               "input": {"arg": "test_auth"}})
            add_rt(SUB, 1, st, "claude-sonnet-5", smsgs, blocks, usage,
                   ["Grep"] if j < 2 else [], stop="tool_use" if j < 2 else "end_turn")
            sub_cache += 2000
            st += 8
        add_hook(A, "SubagentStop", turn, st, {"agent_id": agent_id})
        t = st + 2
    add_hook(A, "Stop", turn, t)
    t += 20

# evento MCP nella sessione A
store.insert_event(
    session_id=A, kind="mcp", subkind="context7:query-docs", turn_index=2,
    ts_start=tA + 120, ts_end=tA + 121.5,
    payload={"server": "context7", "method": "query-docs",
             "params": {"query": "starlette websocket"}, "result_chars": 5400},
)

# ---------------------------------------------------------------- sessione B (chiusa, corta)
B = "0b2c3d4e-7777-8888-9999-aaaabbbbcccc"
tB = NOW - 5400
store.upsert_session(B, tag="demo-breve", title="Fix typo nel README", model="claude-sonnet-5",
                     started_at=tB, ended_at=tB + 90, live=False)
add_hook(B, "SessionStart", 0, tB)
add_hook(B, "UserPromptSubmit", 1, tB + 2, {"prompt": "Correggi i typo nel README"})
bmsgs = [user_msg("Correggi i typo nel README")]
bc = 12000
for i in range(2):
    usage = {"input_tokens": 120, "output_tokens": 500,
             "cache_read_input_tokens": bc, "cache_creation_input_tokens": 800 if i == 0 else 100}
    blocks = ([{"type": "tool_use", "id": f"toolu_b{i}", "name": "Edit", "input": {"arg": "README.md"}}]
              if i == 0 else [{"type": "text", "text": "Typo corretti."}])
    add_rt(B, 1, tB + 4 + i * 10, "claude-sonnet-5", bmsgs, blocks, usage,
           ["Edit"] if i == 0 else [], stop="tool_use" if i == 0 else "end_turn")
    bc += 1000
add_hook(B, "Stop", 1, tB + 30)

store.close()
sessions = Store(DB).get_sessions()
print(f"DB {DB}: {len(sessions)} sessioni")
for s in sessions:
    print(" -", s["id"][:16], s.get("title"), "live" if s.get("live") else "chiusa",
          "rt:", s.get("round_trips"))
