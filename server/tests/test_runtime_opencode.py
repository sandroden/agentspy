"""Tests of the opencode runtime: vocabulary, parser (tool_hint,
last_user_message, command_snippet) and artifact extraction on a plausible
synthetic body."""

from agentspy_server.runtimes import get_runtime
from agentspy_server.runtimes.opencode import OpencodeRuntime

# Synthetic opencode-style body on the Anthropic wire:
# - system as a list of blocks: base prompt + two instruction files injected
#   with the "Instructions from:" prefix (AGENTS.md and CLAUDE.md);
# - an image pasted by the user (message without tool_result);
# - a `read` decided by the LLM (tool_use → tool_result) loading a file;
# - a `bash` (tool_use → tool_result) which is NOT a read file.
SAMPLE_BODY = {
    "system": [
        {"type": "text", "text": "You are opencode."},
        {"type": "text", "text": "Instructions from: /home/u/proj/AGENTS.md\nproject rules"},
        {"type": "text", "text": "Instructions from: /home/u/.claude/CLAUDE.md\nglobal rules"},
    ],
    "tools": [{"name": "read"}, {"name": "bash"}],
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi, look at the image"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "Zm9vYmFy"}},
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_r1", "name": "read", "input": {"filePath": "src/app.ts"}},
                {"type": "tool_use", "id": "toolu_b1", "name": "bash", "input": {"command": "ls"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_r1", "content": "export const x = 1\n"},
                {"type": "tool_result", "tool_use_id": "toolu_b1", "content": "app.ts\n"},
            ],
        },
    ],
}


def _by_kind(artifacts):
    out = {}
    for a in artifacts:
        out.setdefault(a["kind"], []).append(a)
    return out


def test_get_runtime_opencode():
    rt = get_runtime("opencode")
    assert isinstance(rt, OpencodeRuntime)
    assert rt.name == "opencode"


def test_vocabulary():
    rt = OpencodeRuntime()
    assert rt.hook_user_prompt == "chat.message"
    assert rt.hook_pre_tool_use == "tool.execute.before"
    assert rt.hook_post_tool_use == "tool.execute.after"
    assert rt.hook_stop == "session.idle"
    assert rt.session_id_header == ""


def test_helpers_empty_string_does_not_match_by_mistake():
    """Empty vocabulary slots must not match None/"".

    With empty hook_subagent_* and system_reminder_prefix, the helpers in
    base.py must stay false for hook_name None/"" and for any text."""
    rt = OpencodeRuntime()
    assert rt.is_session_end("session.idle") is True
    assert rt.is_session_end("") is False
    assert rt.is_session_end(None) is False
    assert rt.is_subagent_hook("") is False
    assert rt.is_subagent_hook(None) is False
    assert rt.is_tool_call_hook("tool.execute.before") is True
    assert rt.is_tool_call_hook("") is False
    # empty system_reminder_prefix: nothing is a reminder (no "".startswith("")).
    assert rt.is_system_reminder("any text") is False


def test_tool_hint():
    rt = OpencodeRuntime()
    assert rt.tool_hint("read", {"filePath": "src/app.ts"}) == "src/app.ts"
    assert rt.tool_hint("write", {"filePath": "a/b.py", "content": "..."}) == "a/b.py"
    assert rt.tool_hint("bash", {"command": "ls -la /tmp"}) == "ls -la /tmp"
    assert rt.tool_hint("grep", {"pattern": "foo", "path": "src"}) == "foo"
    assert rt.tool_hint("webfetch", {"url": "https://x.dev"}) == "https://x.dev"
    assert rt.tool_hint("task", {"description": "find bugs", "prompt": "..."}) == "find bugs"
    # generic fallback for an unknown tool: first string value
    assert rt.tool_hint("mcp__srv__do", {"q": "hey"}) == "hey"
    assert rt.tool_hint("bash", "non-dict") == ""


def test_command_snippet_always_none():
    rt = OpencodeRuntime()
    assert rt.command_snippet("any text, opencode leaves no markers") is None


def test_last_user_message():
    rt = OpencodeRuntime()
    last = rt.last_user_message(SAMPLE_BODY["messages"])
    assert last is not None
    # the last user message is the one with the tool_result
    assert any(b.get("type") == "tool_result" for b in last["content"])


def test_extract_artifacts_kinds():
    rt = OpencodeRuntime()
    kinds = _by_kind(rt.extract_artifacts(SAMPLE_BODY))
    assert set(kinds) == {"system", "claude-md", "image", "read-file", "tools"}


def test_instruction_files_split_off_from_system():
    rt = OpencodeRuntime()
    kinds = _by_kind(rt.extract_artifacts(SAMPLE_BODY))
    labels = {a["label"] for a in kinds["claude-md"]}
    assert labels == {"AGENTS.md", "CLAUDE.md"}
    # not additive: the system prompt weighs only the base prompt, not the
    # instruction files (which have a chip of their own).
    system = kinds["system"][0]
    assert system["chars"] < len("Instructions from: /home/u/proj/AGENTS.md")
    assert all(a["chars"] > 0 for a in kinds["claude-md"])


def test_read_file_only_for_read_not_bash():
    rt = OpencodeRuntime()
    read_files = _by_kind(rt.extract_artifacts(SAMPLE_BODY))["read-file"]
    assert len(read_files) == 1
    assert read_files[0]["path"] == "src/app.ts"


def test_extract_artifacts_robust():
    rt = OpencodeRuntime()
    assert rt.extract_artifacts(None) == []
    assert rt.extract_artifacts({}) == []
    assert rt.extract_artifacts({"messages": "not-a-list"}) == []


def test_non_instruction_block_after_agents_is_not_attributed_to_it():
    """If other system blocks (mcp/skills) follow an instruction file, their
    weight must stay on the system, not end up in the file's char count."""
    rt = OpencodeRuntime()
    body = {
        "system": [
            {"type": "text", "text": "Instructions from: /p/AGENTS.md\nrules"},
            {"type": "text", "text": "<mcp_instructions>" + "M" * 500 + "</mcp_instructions>"},
        ],
    }
    kinds = _by_kind(rt.extract_artifacts(body))
    agents = kinds["claude-md"][0]
    assert agents["chars"] == len("Instructions from: /p/AGENTS.md\nrules")
    assert kinds["system"][0]["chars"] >= 500


def test_extract_system_as_string():
    """The system can arrive as a concatenated string: the instruction split
    must work in that case too."""
    rt = OpencodeRuntime()
    body = {
        "system": "You are opencode.\nInstructions from: /p/AGENTS.md\ncontent",
    }
    kinds = _by_kind(rt.extract_artifacts(body))
    assert kinds["claude-md"][0]["label"] == "AGENTS.md"
    assert kinds["system"][0]["chars"] > 0


def test_instructions_inside_a_single_block():
    """Real shape observed on the wire (opencode 1.18, E2E of 2026-07-16): the
    system is ONE block concatenating the base prompt, several instruction
    files (whose content may contain blank lines) and the skills section at the
    end. Each file must be split out up to the start of the next section, not
    up to the end of the block nor up to the first blank line."""
    rt = OpencodeRuntime()
    claude_md = "Instructions from: /home/u/.claude/CLAUDE.md\n# Repo\nrule\n\n# Python\nanother rule\n"
    agents_md = "Instructions from: /p/AGENTS.md\n# Rules\na single sentence.\n\n"
    skills = "Skills provide specialized instructions and workflows for specific tasks.\n<available_skills>" + "S" * 300
    body = {"system": [{"type": "text", "text": "You are OpenCode.\n<env>...</env>\n" + claude_md + agents_md + skills}]}
    kinds = _by_kind(rt.extract_artifacts(body))
    per_label = {a["label"]: a["chars"] for a in kinds["claude-md"]}
    assert per_label["CLAUDE.md"] == len(claude_md)
    assert per_label["AGENTS.md"] == len(agents_md)
    # base + skills stay on the system, without double counting
    assert kinds["system"][0]["chars"] == len("You are OpenCode.\n<env>...</env>\n") + len(skills)
