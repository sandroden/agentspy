"""Registry dei runtime dell'agente.

Il runtime attivo si sceglie con AGENTSPY_RUNTIME (default: claude-code).
Per aggiungerne uno: implementare AgentRuntime in un modulo qui accanto e
registrarlo in RUNTIMES.
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
            f"runtime sconosciuto: {name!r} (disponibili: {', '.join(sorted(RUNTIMES))})"
        ) from None


__all__ = ["AgentRuntime", "RUNTIMES", "get_runtime"]
