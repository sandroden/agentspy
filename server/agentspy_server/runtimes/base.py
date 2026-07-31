"""Runtime layer: isolates the conventions of the agent runtime generating the traffic.

Mirror image of ``providers/base.py`` — there the LLM provider's wire protocol,
here everything specific to the *coding agent* talking to the provider (today
Claude Code). This is knowledge distinct from the protocol: how the agent marks
requests with the session id, the names of its hooks, the bridge tying MCP
events to the conversation, the way it injects instructions/attachments into the
context, the tool-name → argument maps for the snippets.

The rest of the system (Correlator, ingest, Store) knows none of these strings:
it asks an ``AgentRuntime`` for them. Supporting another runtime (e.g. opencode)
then means writing a single new module that declares its own vocabulary and
implements the few custom parsers, without touching correlation.

The base class declares the vocabulary (string attributes) and derives the
generic helpers from it; only the parsers that are genuinely runtime-specific
stay ``@abstractmethod`` (last user message, tool hints, command snippets,
context artifact inventory).

Note on the layer boundary: the FIELD NAMES of the hook payload (``session_id``,
``prompt``, ``tool_use_id``, ``tool_name``, ``agent_id``…) do not go through
here — they are the neutral format of the ingest API (``POST /ingest/hook``).
For a runtime whose native events have a different shape, translating into that
format is the job of the hook script/plugin on the agent side, not the server's.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AgentRuntime(ABC):
    """Everything agentspy needs to know about an agent runtime's conventions."""

    name: str = "?"

    # -- vocabulary (declared by subclasses) ------------------------------
    # Header with which the runtime marks EVERY request with the session id.
    session_id_header: str = ""
    # Hook names, for correlation semantics.
    hook_user_prompt: str = ""  # advances the turn
    hook_pre_tool_use: str = ""  # carries the tool_use_id for the MCP/subagent join
    hook_post_tool_use: str = ""  # tool call outcome (presentation only)
    hook_subagent_start: str = ""  # opens a child session (marker on the parent)
    hook_subagent_stop: str = ""  # closes the child session (marker on the parent)
    hook_stop: str = ""  # closes the main session
    # Key with which the runtime passes the tool_use id inside the JSON-RPC tools/call.
    mcp_tool_use_id_key: str = ""
    # Prefix of the reminder blocks the runtime puts alongside the user prompt.
    system_reminder_prefix: str = ""

    # -- generic helpers derived from the vocabulary ----------------------

    def is_subagent_hook(self, hook_name: str | None) -> bool:
        """True if the hook opens/closes a subagent (marker on the parent timeline)."""
        return bool(hook_name) and hook_name in (self.hook_subagent_start, self.hook_subagent_stop)

    def is_session_end(self, hook_name: str | None) -> bool:
        """True if the hook closes the session (main or subagent)."""
        return bool(hook_name) and hook_name in (self.hook_stop, self.hook_subagent_stop)

    def is_tool_call_hook(self, hook_name: str | None) -> bool:
        """True if the hook describes a tool call (carries tool_name/tool_input)."""
        return bool(hook_name) and hook_name in (self.hook_pre_tool_use, self.hook_post_tool_use)

    def tool_use_id_from_mcp_meta(self, meta: dict | None) -> str | None:
        """Tool_use id carried in the ``params._meta`` of an MCP tools/call."""
        return (meta or {}).get(self.mcp_tool_use_id_key)

    def is_system_reminder(self, text: str) -> bool:
        """True if the text is a reminder block injected by the runtime.

        With an empty ``system_reminder_prefix`` (runtime without the notion of a
        reminder alongside the prompt) nothing is a reminder: without this guard
        ``"".startswith("")`` would discard EVERY text block."""
        return bool(self.system_reminder_prefix) and isinstance(text, str) and text.startswith(
            self.system_reminder_prefix
        )

    # -- runtime-specific parsers -----------------------------------------

    @abstractmethod
    def last_user_message(self, messages: list[Any]) -> dict | None:
        """Last message actually coming from the user.

        Not necessarily ``messages[-1]``: some runtimes append service messages
        (e.g. Claude Code appends a ``role:"system"``) that would mask the user
        prompt from the binding and the turn heuristic.
        """

    @abstractmethod
    def tool_hint(self, name: str | None, tool_input: Any) -> str:
        """Compact hint of a tool call's argument (for the badges)."""

    @abstractmethod
    def command_snippet(self, text: str) -> str | None:
        """Clean ``/name args`` snippet if the text is the expansion of a runtime
        slash-command / skill, otherwise None."""

    @abstractmethod
    def extract_artifacts(self, body: Any) -> list[dict[str, Any]]:
        """Educational inventory of the artifacts making up the request.

        Extracts from the ``body`` the elements entering the context (system
        prompt, instruction files, images, attachments, tools): how the runtime
        injects them is its own knowledge.
        """

    # Labels that ``service_label`` returns when it recognizes the FAMILY of
    # the traffic but not its exact kind. They fill the field like any other
    # label, but never overwrite a sharper one found on another round trip of
    # the same session — otherwise the arrival order would decide the name.
    generic_service_labels: frozenset[str] = frozenset()

    def service_label(self, body: Any) -> str | None:
        """Kind of service traffic the request belongs to, or None if unknown.

        A CLI does not only run the user's conversation: it also spends model
        calls on its own machinery (safety checks, suggestions, probes). They
        all land in synthetic sessions and look alike in the sidebar, while
        doing very different things. The request itself says which is which —
        the runtime knows the prompts. Concrete (returns None) so a runtime can
        ignore the question: the caller falls back to a generic label.
        """
        return None

    def extract_artifact_content(self, body: Any, key: str) -> dict[str, Any] | None:
        """Content of a single artifact of the request, for the "read it" view.

        ``key`` is ``"{kind}|{path or label}"``, the same identity the UI uses.
        Concrete (not abstract) so a runtime can ship the inventory without the
        content reading: the default is "not available", the UI degrades to a
        message.
        """
        return None
