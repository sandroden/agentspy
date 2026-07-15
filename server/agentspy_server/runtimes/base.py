"""Strato runtime: isola le convenzioni dell'agent runtime che genera il traffico.

Speculare a ``providers/base.py`` — lì il protocollo wire del provider LLM, qui
tutto ciò che è specifico del *coding agent* che parla col provider (oggi Claude
Code). Sono conoscenze diverse dal protocollo: come l'agent marca le richieste
con l'id di sessione, i nomi dei suoi hook, il ponte che lega gli eventi MCP alla
conversazione, il modo in cui inietta istruzioni/allegati nel contesto, le mappe
nome-tool → argomento per gli snippet.

Il resto del sistema (Correlator, ingest, Store) non conosce nessuna di queste
stringhe: le chiede a un ``AgentRuntime``. Supportare un altro runtime (es.
opencode) significa allora scrivere un solo modulo nuovo che dichiara il proprio
vocabolario e implementa i pochi parser custom, senza toccare la correlazione.

La classe base dichiara il vocabolario (attributi stringa) e ne deriva gli helper
generici; restano ``@abstractmethod`` solo i parser davvero specifici del
runtime (ultimo messaggio utente, hint dei tool, snippet dei comandi, inventario
degli artefatti del contesto).

Nota sul confine del layer: i NOMI DEI CAMPI del payload hook (``session_id``,
``prompt``, ``tool_use_id``, ``tool_name``, ``agent_id``…) non passano da qui —
sono il formato neutro dell'API di ingest (``POST /ingest/hook``). Per un
runtime i cui eventi nativi hanno altra forma, la traduzione in quel formato è
compito dello script hook/plugin lato agente, non del server.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AgentRuntime(ABC):
    """Tutto ciò che agentspy deve sapere delle convenzioni di un agent runtime."""

    name: str = "?"

    # -- vocabolario (dichiarato dalle sottoclassi) -----------------------
    # Header con cui il runtime marca OGNI richiesta con l'id della sessione.
    session_id_header: str = ""
    # Nomi hook, per la semantica della correlazione.
    hook_user_prompt: str = ""  # avanza il turno
    hook_pre_tool_use: str = ""  # porta il tool_use_id per il join MCP/subagente
    hook_post_tool_use: str = ""  # esito della chiamata tool (solo presentazione)
    hook_subagent_start: str = ""  # apre una sessione figlia (marker sulla madre)
    hook_subagent_stop: str = ""  # chiude la sessione figlia (marker sulla madre)
    hook_stop: str = ""  # chiude la sessione principale
    # Chiave con cui il runtime passa il tool_use id dentro la tools/call JSON-RPC.
    mcp_tool_use_id_key: str = ""
    # Prefisso dei blocchi di reminder che il runtime affianca al prompt utente.
    system_reminder_prefix: str = ""

    # -- helper generici derivati dal vocabolario -------------------------

    def is_subagent_hook(self, hook_name: str | None) -> bool:
        """True se l'hook apre/chiude un subagente (marker sulla timeline madre)."""
        return hook_name in (self.hook_subagent_start, self.hook_subagent_stop)

    def is_session_end(self, hook_name: str | None) -> bool:
        """True se l'hook chiude la sessione (principale o subagente)."""
        return hook_name in (self.hook_stop, self.hook_subagent_stop)

    def is_tool_call_hook(self, hook_name: str | None) -> bool:
        """True se l'hook descrive una chiamata tool (porta tool_name/tool_input)."""
        return hook_name in (self.hook_pre_tool_use, self.hook_post_tool_use)

    def tool_use_id_from_mcp_meta(self, meta: dict | None) -> str | None:
        """Tool_use id trasportato nel ``params._meta`` di una tools/call MCP."""
        return (meta or {}).get(self.mcp_tool_use_id_key)

    def is_system_reminder(self, text: str) -> bool:
        """True se il testo è un blocco di reminder iniettato dal runtime."""
        return isinstance(text, str) and text.startswith(self.system_reminder_prefix)

    # -- parser specifici del runtime -------------------------------------

    @abstractmethod
    def last_user_message(self, messages: list[Any]) -> dict | None:
        """Ultimo messaggio realmente proveniente dall'utente.

        Non è per forza ``messages[-1]``: alcuni runtime accodano messaggi di
        servizio (es. Claude Code accoda un ``role:"system"``) che
        maschererebbero il prompt dell'utente al binding e all'euristica turno.
        """

    @abstractmethod
    def tool_hint(self, name: str | None, tool_input: Any) -> str:
        """Indizio compatto dell'argomento di una chiamata tool (per i badge)."""

    @abstractmethod
    def command_snippet(self, text: str) -> str | None:
        """Snippet pulito ``/nome args`` se il testo è l'espansione di uno
        slash-command / skill del runtime, altrimenti None."""

    @abstractmethod
    def extract_artifacts(self, body: Any) -> list[dict[str, Any]]:
        """Inventario didattico degli artefatti che compongono la richiesta.

        Estrae dal ``body`` gli elementi che entrano nel contesto (system prompt,
        file di istruzioni, immagini, allegati, tool): come il runtime li inietta
        è conoscenza sua.
        """
