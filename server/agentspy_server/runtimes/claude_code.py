"""Runtime Claude Code: le convenzioni specifiche del CLI di Claude Code.

Raccoglie in un solo posto le stringhe e i parser che il resto del sistema
tratterebbe altrimenti come costanti cablate: nomi hook, header di sessione,
chiave del ponte MCP, mappe nome-tool → argomento, parsing degli slash-command.
L'inventario degli artefatti del contesto (regex "Contents of…", "Called the X
tool", ecc.) vive in ``claude_code_artifacts`` ed è esposto qui come metodo.
"""

from __future__ import annotations

from typing import Any

from .base import AgentRuntime
from .claude_code_artifacts import extract_artifacts


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

    # Claude Code (cli >= 2.x) manda questo header su OGNI richiesta con l'id
    # della sessione: discrimina run concorrenti con lo stesso primo prompt.
    session_id_header = "x-claude-code-session-id"

    hook_user_prompt = "UserPromptSubmit"
    hook_pre_tool_use = "PreToolUse"
    hook_post_tool_use = "PostToolUse"
    hook_subagent_start = "SubagentStart"
    hook_subagent_stop = "SubagentStop"
    hook_stop = "Stop"

    # Il tool_use id della conversazione API viaggia nel params._meta della
    # tools/call JSON-RPC verso i server MCP.
    mcp_tool_use_id_key = "claudecode/toolUseId"

    system_reminder_prefix = "<system-reminder>"

    def last_user_message(self, messages: list[Any]) -> dict | None:
        """Ultimo messaggio con role='user'. NON basta messages[-1]: Claude Code
        (cli >= 2.1) accoda alla richiesta un messaggio con role='system' (es. il
        reminder dei deferred tools), che maschererebbe il prompt dell'utente sia
        al binding via prompt sia all'euristica del turno."""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                return m
        return None

    def tool_hint(self, name: str | None, tool_input: Any) -> str:
        """Indizio compatto dell'argomento di una chiamata tool, per i badge in
        timeline: path per i tool su file, inizio comando per Bash, url/query per
        i tool web, pattern per le ricerche. Best-effort, stringa vuota se non
        riconosciuto."""
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
                # fallback generico (incluso mcp__*): il primo valore stringa
                v = next((x for x in tool_input.values() if isinstance(x, str) and x), None)
            if isinstance(v, str):
                v = " ".join(v.split())  # su una riga
                return v[:200]
        except Exception:
            pass
        return ""

    def command_snippet(self, text: str) -> str | None:
        """Se il testo è l'espansione di uno slash-command / skill
        (`<command-name>…`), restituisce uno snippet pulito `/nome args` invece
        dell'XML del wrapper + lo SKILL.md iniettato. Altrimenti None."""
        if "<command-name>" not in text:
            return None
        name = _extract_tag(text, "command-name")
        if not name:
            return None
        args = _extract_tag(text, "command-args") or ""
        return f"{name} {args}".strip()[:160]

    def extract_artifacts(self, body: Any) -> list[dict[str, Any]]:
        return extract_artifacts(body)
