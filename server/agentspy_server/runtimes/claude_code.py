"""Claude Code runtime: the conventions specific to the Claude Code CLI.

Collects in one place the strings and parsers the rest of the system would
otherwise treat as hard-wired constants: hook names, session header, MCP bridge
key, tool-name → argument maps, slash-command parsing. The context artifact
inventory (regexes "Contents of…", "Called the X tool", etc.) lives in
``claude_code_artifacts`` and is exposed here as a method.
"""

from __future__ import annotations

from typing import Any

from .base import AgentRuntime
from .claude_code_artifacts import extract_artifact_content, extract_artifacts


def _extract_tag(text: str, tag: str) -> str | None:
    open_t, close_t = f"<{tag}>", f"</{tag}>"
    i = text.find(open_t)
    if i == -1:
        return None
    j = text.find(close_t, i + len(open_t))
    if j == -1:
        return None
    return text[i + len(open_t) : j].strip()


class ClaudeCodeRuntime(AgentRuntime):
    name = "claude-code"

    # Claude Code (cli >= 2.x) sends this header on EVERY request with the
    # session id: it tells apart concurrent runs with the same first prompt.
    session_id_header = "x-claude-code-session-id"

    hook_user_prompt = "UserPromptSubmit"
    hook_pre_tool_use = "PreToolUse"
    hook_post_tool_use = "PostToolUse"
    hook_subagent_start = "SubagentStart"
    hook_subagent_stop = "SubagentStop"
    hook_stop = "Stop"

    # The tool_use id of the API conversation travels in the params._meta of
    # the JSON-RPC tools/call towards the MCP servers.
    mcp_tool_use_id_key = "claudecode/toolUseId"

    system_reminder_prefix = "<system-reminder>"

    def last_user_message(self, messages: list[Any]) -> dict | None:
        """Last message with role='user'. messages[-1] is NOT enough: Claude Code
        (cli >= 2.1) appends to the request a message with role='system' (e.g. the
        deferred tools reminder), which would mask the user prompt both from the
        binding via prompt and from the turn heuristic."""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                return m
        return None

    def tool_hint(self, name: str | None, tool_input: Any) -> str:
        """Compact hint of a tool call's argument, for the timeline badges: path
        for file tools, start of the command for Bash, url/query for the web
        tools, pattern for searches. Best-effort, empty string if not
        recognised."""
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
                # generic fallback (mcp__* included): the first string value
                v = next((x for x in tool_input.values() if isinstance(x, str) and x), None)
            if isinstance(v, str):
                v = " ".join(v.split())  # on one line
                return v[:200]
        except Exception:
            pass
        return ""

    def command_snippet(self, text: str) -> str | None:
        """If the text is the expansion of a slash-command / skill
        (`<command-name>…`), returns a clean `/name args` snippet instead of the
        wrapper XML + the injected SKILL.md. Otherwise None."""
        if "<command-name>" not in text:
            return None
        name = _extract_tag(text, "command-name")
        if not name:
            return None
        args = _extract_tag(text, "command-args") or ""
        return f"{name} {args}".strip()[:160]

    def extract_artifacts(self, body: Any) -> list[dict[str, Any]]:
        return extract_artifacts(body)

    def extract_artifact_content(self, body: Any, key: str) -> dict[str, Any] | None:
        return extract_artifact_content(body, key)
