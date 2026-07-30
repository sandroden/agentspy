"""Registry of the agent runtimes.

The active runtime is selected with AGENTSPY_RUNTIME (default: claude-code).
To add one: implement AgentRuntime in a module next to this one and register
it in RUNTIMES.
"""

from __future__ import annotations

import os

from .base import AgentRuntime
from .claude_code import ClaudeCodeRuntime
from .opencode import OpencodeRuntime

RUNTIMES: dict[str, type[AgentRuntime]] = {
    "claude-code": ClaudeCodeRuntime,
    "opencode": OpencodeRuntime,
}


def get_runtime(name: str | None = None) -> AgentRuntime:
    name = name or os.environ.get("AGENTSPY_RUNTIME", "claude-code")
    try:
        return RUNTIMES[name]()
    except KeyError:
        raise ValueError(
            f"unknown runtime: {name!r} (available: {', '.join(sorted(RUNTIMES))})"
        ) from None


__all__ = ["AgentRuntime", "RUNTIMES", "get_runtime"]
