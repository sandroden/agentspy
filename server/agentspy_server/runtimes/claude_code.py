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


# Opening words of the system prompts that identify service traffic. Matched as
# a prefix, so a revision of the body of the prompt does not break recognition.
_SECURITY_MONITOR_PREFIX = "You are a security monitor for autonomous AI coding agents"
_AGENT_SDK_PREFIX = "You are a Claude agent, built on Anthropic's Claude Agent SDK"

# Suggestions and title generation share the system prompt with a real
# conversation: the only discriminant is the marker opening the injected user
# message. Title generation wraps the conversation in <session>…</session> and
# then asks for the title (in the user's language, so the instruction that
# follows is not a stable marker — the wrapper is).
_SUGGESTION_MARKER = "[SUGGESTION MODE"
_TITLE_MARKER = "<session>"

# The marker opens its block; scanning the whole transcript (tens of thousands
# of characters per request) to find it elsewhere would cost more than it gives.
_MARKER_WINDOW = 200


def _system_starts_with(body: dict, prefix: str) -> bool:
    """True if a system block opens with ``prefix``.

    Checked block by block, not on their concatenation: Claude Code sends
    `system` as a list whose FIRST block is the billing header
    (`x-anthropic-billing-header: …`), so the prompt that identifies the
    traffic is never at offset 0. Also accepts the plain-string shape.
    """
    system = body.get("system")
    if isinstance(system, str):
        return system.startswith(prefix)
    if not isinstance(system, list):
        return False
    return any(
        isinstance(b, dict) and isinstance(b.get("text"), str) and b["text"].startswith(prefix)
        for b in system
    )


def _has_marker(body: dict, marker: str) -> bool:
    """True if a message block opens with ``marker`` (see _MARKER_WINDOW)."""
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        blocks = content if isinstance(content, list) else [content]
        for block in blocks:
            text = block.get("text") if isinstance(block, dict) else block
            if isinstance(text, str) and marker in text[:_MARKER_WINDOW]:
                return True
    return False


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

    # The safety monitor without a stop sequence: the family is certain, the
    # stage is not. Measured: it coexists with the sharper variant in the same
    # session (43 round trips at `</block>` + 1 with no stop sequence), so
    # without this the label would depend on which one arrived first.
    generic_service_labels = frozenset({"security monitor"})

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

    def service_label(self, body: Any) -> str | None:
        """Which piece of CLI machinery this request belongs to.

        Every discriminant below was read off the live DB, never guessed: see
        the table in the OKF note (/design/service-traffic.md). The order
        matters — the safety monitor is recognized by its own system prompt,
        while suggestions run on the SAME `You are Claude Code…` prompt as a
        real conversation and are only told apart by the marker in the
        messages.
        """
        if not isinstance(body, dict):
            return None

        if _system_starts_with(body, _SECURITY_MONITOR_PREFIX):
            # Two-stage design, stated by the prompt itself: stage 1 grades the
            # harm of the action alone and stops at </severity>; stage 2 weighs
            # user intent and stops at </block>. A variant with no stop sequence
            # stays generic rather than being forced into one of the two.
            stops = body.get("stop_sequences") or []
            if "</severity>" in stops:
                return "security 1"
            if "</block>" in stops:
                return "security 2"
            return "security monitor"

        if _system_starts_with(body, _AGENT_SDK_PREFIX):
            return "agent sdk"

        # A single output token: the CLI is not asking for text, it is probing
        # (the message body is literally "quota").
        if body.get("max_tokens") == 1:
            return "quota"

        if _has_marker(body, _SUGGESTION_MARKER):
            return "suggestions"

        if _has_marker(body, _TITLE_MARKER):
            return "title"

        # Everything else stays unrecognized ON PURPOSE: a synthetic session not
        # yet bound to its parent carries a normal conversation, byte for byte,
        # and inventing a label for it would be worse than the generic one.
        return None

    def extract_artifacts(self, body: Any) -> list[dict[str, Any]]:
        return extract_artifacts(body)

    def extract_artifact_content(self, body: Any, key: str) -> dict[str, Any] | None:
        return extract_artifact_content(body, key)
