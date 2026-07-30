"""opencode runtime: the conventions of the opencode CLI (https://opencode.ai)
used with Anthropic models via API key.

Mirror image of ``claude_code``. Main differences, reflected in the vocabulary:

- **Native hook names.** The tool is educational: the data must mirror the
  reality of the runtime. The ``hook_event_name`` values are the names of the
  opencode plugin API events (``chat.message``, ``tool.execute.before/after``,
  ``session.idle``), not renamed to the Claude Code labels. Translating native
  event → neutral ingest fields is done by the plugin
  ``hooks/opencode/agentspy.js``.
- **No session header.** opencode does not mark HTTP requests with a session
  id: ``session_id_header`` is empty and the round trip → session correlation
  happens by fingerprint + plugin events.
- **Missing concepts.** opencode has no dedicated subagent start/stop hooks
  (they run as child sessions with ``parentID``), no system-reminder wrapper
  around the user prompt, and no verified MCP bridge: the corresponding
  vocabulary slots stay empty strings. The ``base.py`` helpers were made robust
  to empty strings (a ``bool(...)`` guard prevents an empty slot from matching
  ``None``/``""`` by mistake).

The artifact inventory lives in ``opencode_artifacts``.
"""

from __future__ import annotations

from typing import Any

from .base import AgentRuntime
from .opencode_artifacts import extract_artifacts

# Native opencode tools → input field carrying the salient argument, for the
# timeline badges. Names verified against the sources (packages/opencode/src/
# tool/*.ts): camelCase schema, file tools with ``filePath``.
_HINT_KEYS: dict[str, tuple[str, ...]] = {
    "read": ("filePath",),
    "write": ("filePath",),
    "edit": ("filePath",),
    "bash": ("command",),
    "grep": ("pattern",),
    "glob": ("pattern",),
    "webfetch": ("url",),
    "websearch": ("query",),
    "task": ("description", "prompt"),
}


class OpencodeRuntime(AgentRuntime):
    name = "opencode"

    # opencode does not send a header with the session id: the round trip →
    # session correlation is by fingerprint + plugin events.
    session_id_header = ""

    # NATIVE names of the opencode plugin API events.
    hook_user_prompt = "chat.message"
    hook_pre_tool_use = "tool.execute.before"
    hook_post_tool_use = "tool.execute.after"
    # opencode has no dedicated subagent start/stop hooks: they run as child
    # sessions (parentID), correlation not implemented yet.
    hook_subagent_start = ""
    hook_subagent_stop = ""
    # session.idle closes the turn: like Claude Code's Stop it fires at the end
    # of every assistant response, not only at the end of the session.
    hook_stop = "session.idle"

    # The callID of the tool hooks IS the toolu_… on the wire (verified in E2E),
    # and the plugin sends it as tool_use_id. Not verified instead that opencode
    # passes the id in the _meta of MCP tools/call: left empty until observed.
    mcp_tool_use_id_key = ""

    # opencode does not put system-reminder blocks alongside the user prompt.
    system_reminder_prefix = ""

    def last_user_message(self, messages: list[Any]) -> dict | None:
        """Last message with role='user'. opencode does not append service
        messages (as Claude Code does with ``role:'system'``), so here the last
        ``role:'user'`` is enough."""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                return m
        return None

    def tool_hint(self, name: str | None, tool_input: Any) -> str:
        """Compact hint of a tool call's argument, for the timeline badges.
        Best-effort, empty string if not recognised."""
        if not isinstance(tool_input, dict):
            return ""
        try:
            keys = _HINT_KEYS.get(name or "")
            v: Any = None
            if keys:
                v = next((tool_input.get(k) for k in keys if isinstance(tool_input.get(k), str) and tool_input.get(k)), None)
            if v is None:
                # generic fallback (mcp__* included): path if present, then the
                # first non-empty string value.
                for k in ("filePath", "file_path", "path"):
                    val = tool_input.get(k)
                    if isinstance(val, str) and val:
                        v = val
                        break
                if v is None:
                    v = next((x for x in tool_input.values() if isinstance(x, str) and x), None)
            if isinstance(v, str):
                return " ".join(v.split())[:200]
        except Exception:
            pass
        return ""

    def command_snippet(self, text: str) -> str | None:
        """opencode expands slash-commands server-side by replacing the text of
        the user message, without leaving a recognisable marker on the wire:
        there is nothing to clean up, hence None."""
        return None

    def extract_artifacts(self, body: Any) -> list[dict[str, Any]]:
        return extract_artifacts(body)
