"""Runtime opencode: le convenzioni del CLI opencode (https://opencode.ai) usato
con modelli Anthropic via API key.

Speculare a ``claude_code``. Differenze principali, riflesse nel vocabolario:

- **Nomi hook nativi.** Lo strumento è didattico: i dati devono rispecchiare la
  realtà del runtime. Gli ``hook_event_name`` sono i nomi degli eventi del
  plugin API di opencode (``chat.message``, ``tool.execute.before/after``,
  ``session.idle``), non ribattezzati alle etichette di Claude Code. La
  traduzione evento nativo → campi neutri dell'ingest la fa il plugin
  ``hooks/opencode/agentspy.js``.
- **Nessun header di sessione.** opencode non marca le richieste HTTP con un id
  di sessione: ``session_id_header`` è vuoto e la correlazione round trip →
  sessione avviene per fingerprint + eventi del plugin.
- **Concetti assenti.** opencode non ha hook dedicati di start/stop dei
  subagenti (girano come sessioni figlie con ``parentID``), né un wrapper di
  system-reminder attorno al prompt utente, né un ponte MCP verificato: i
  relativi slot del vocabolario restano stringa vuota. Gli helper di ``base.py``
  sono stati resi robusti alle stringhe vuote (una guardia ``bool(...)`` evita
  che uno slot vuoto matchi per sbaglio ``None``/``""``).

L'inventario degli artefatti vive in ``opencode_artifacts``.
"""

from __future__ import annotations

from typing import Any

from .base import AgentRuntime
from .opencode_artifacts import extract_artifacts

# Tool nativi di opencode → campo dell'input che porta l'argomento saliente,
# per i badge in timeline. Nomi verificati sui sorgenti (packages/opencode/src/
# tool/*.ts): schema camelCase, tool su file con ``filePath``.
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

    # opencode non manda un header con l'id di sessione: la correlazione round
    # trip → sessione è per fingerprint + eventi del plugin.
    session_id_header = ""

    # Nomi NATIVI degli eventi del plugin API di opencode.
    hook_user_prompt = "chat.message"
    hook_pre_tool_use = "tool.execute.before"
    hook_post_tool_use = "tool.execute.after"
    # opencode non ha hook dedicati di start/stop dei subagenti: girano come
    # sessioni figlie (parentID), correlazione non ancora implementata.
    hook_subagent_start = ""
    hook_subagent_stop = ""
    # session.idle chiude il turno: come lo Stop di Claude Code scatta a fine di
    # ogni risposta dell'assistente, non solo a fine sessione.
    hook_stop = "session.idle"

    # Il callID degli hook tool È il toolu_… della wire (verificato in E2E), e il
    # plugin lo manda come tool_use_id. Non verificato invece che opencode passi
    # l'id nel _meta delle tools/call MCP: lasciato vuoto finché non osservato.
    mcp_tool_use_id_key = ""

    # opencode non affianca al prompt utente blocchi di system-reminder.
    system_reminder_prefix = ""

    def last_user_message(self, messages: list[Any]) -> dict | None:
        """Ultimo messaggio con role='user'. opencode non accoda messaggi di
        servizio (come fa Claude Code col ``role:'system'``), quindi qui basta
        l'ultimo ``role:'user'``."""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                return m
        return None

    def tool_hint(self, name: str | None, tool_input: Any) -> str:
        """Indizio compatto dell'argomento di una chiamata tool, per i badge in
        timeline. Best-effort, stringa vuota se non riconosciuto."""
        if not isinstance(tool_input, dict):
            return ""
        try:
            keys = _HINT_KEYS.get(name or "")
            v: Any = None
            if keys:
                v = next((tool_input.get(k) for k in keys if isinstance(tool_input.get(k), str) and tool_input.get(k)), None)
            if v is None:
                # fallback generico (incluso mcp__*): path se presente, poi il
                # primo valore stringa non vuoto.
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
        """opencode espande gli slash-command lato server sostituendo il testo del
        messaggio utente, senza lasciare un marcatore riconoscibile sulla wire:
        non c'è nulla da ripulire, quindi None."""
        return None

    def extract_artifacts(self, body: Any) -> list[dict[str, Any]]:
        return extract_artifacts(body)
