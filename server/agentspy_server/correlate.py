"""Assegna i round trip del proxy e gli eventi hook/mcp a sessioni/turni/subagenti.

Il traffico HTTP verso l'API Anthropic non porta session_id: lo ricaviamo con
le regole descritte in PLAN.md ("Correlazione"), in ordine di forza:

1. ``tool_use_id``: l'hook ``PreToolUse`` porta ``session_id`` + ``tool_use_id``;
   il round trip precedente conteneva un blocco ``tool_use`` con quell'id
   (``toolu_...``) prodotto dal modello: lega la conversazione API alla sessione
   hook, sostituendo la sessione sintetica creata fino a quel momento.
2. ``UserPromptSubmit``: quando arriva, avanza il turno (``turn_index += 1``)
   in modo autoritativo per quella sessione (da quel momento la sessione ha
   "hooks attivi" e l'euristica sul testo utente viene disattivata).
3. **Fingerprint di conversazione**: sha256 di (system serializzato + primo
   messaggio user). Round trip successivi con lo stesso fingerprint (la
   conversazione cresce: più messages, stesso prefisso) vengono incatenati
   alla stessa sessione, anche senza alcun hook.
4. Header ``x-agentspy-tag`` → tag della sessione (round trip) o campo ``tag``
   del body di ingest (hook/mcp).
5. ``SubagentStart``/``SubagentStop`` → sessione figlia con
   ``parent_session_id``, agganciata al genitore tramite il ``tool_use_id``
   della chiamata Task/Agent (stesso meccanismo del punto 1) o, se il payload
   dell'hook lo fornisce già esplicitamente, tramite ``parent_session_id``.

Limiti noti (MVP, degradano senza rompersi):
* Senza alcun hook, tutte le sessioni sono sintetiche (``syn-<fingerprint[:12]>``)
  e i turni sono euristici: nuovo turno quando l'ultimo messaggio ``user`` del
  round trip è testuale e NON è un risultato di tool (``tool_result``), e il
  testo differisce dall'ultimo prompt visto per quella sessione.
* Il fingerprint usa system + primo messaggio user: due conversazioni distinte
  con lo *stesso* system prompt e lo stesso primissimo messaggio (raro ma
  possibile con prompt di test identici) collidono nella stessa sessione
  sintetica finché non arriva un hook a disambiguarle.
* Lo schema esatto dei payload hook di Claude Code (nomi dei campi per
  ``SubagentStart``/``SubagentStop``) non è stato verificato empiricamente in
  questa fase (F5 lo farà con sessioni reali); qui si accettano più varianti
  ragionevoli di nome campo (``parent_tool_use_id``/``tool_use_id``,
  ``parent_session_id`` esplicito se presente) per essere robusti a piccole
  differenze di schema.
* Richieste fuori ordine (retry/parallelismo) non sono gestite esplicitamente:
  l'euristica turno può comportarsi in modo imprevedibile se i round trip
  arrivano al collector in un ordine diverso da quello temporale reale.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


def _strip_volatile(obj):
    """Rimuove ricorsivamente i campi che variano fra round trip della stessa
    conversazione: i marker ``cache_control`` si spostano quando il checkpoint
    di cache avanza, e cambierebbero il fingerprint di una conversazione che
    in realtà è la stessa."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


def fingerprint(system, first_user_message) -> str:
    """sha256 di (system serializzato + primo messaggio user), usato per
    incatenare round trip della stessa conversazione senza hook."""
    payload = json.dumps(_strip_volatile(system), sort_keys=True, ensure_ascii=False) + "|" + json.dumps(
        _strip_volatile(first_user_message), sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_user_text(content) -> str | None:
    """Testo del messaggio user, se presente. Concatena TUTTI i blocchi 'text':
    Claude Code affianca al prompt dell'utente blocchi di system-reminder, e il
    solo primo blocco potrebbe essere identico fra turni diversi."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            b.get("text") or ""
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        if texts:
            return "\n".join(texts)
    return None


def _is_tool_result_message(content) -> bool:
    """True se il messaggio user è (anche solo in parte) un tool_result:
    continuazione automatica del loop tool, non un nuovo turno utente."""
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
    return False


@dataclass
class SessionState:
    turn_index: int = 0
    last_user_text: str | None = None
    tag: str | None = None
    agent_id: str | None = None
    parent_session_id: str | None = None
    has_hooks: bool = False
    fingerprints: set = field(default_factory=set)


class Correlator:
    """Stato di correlazione in memoria. Metodi puri sui dati passati, senza I/O."""

    def __init__(self):
        self.session_state: dict[str, SessionState] = {}
        self.fingerprint_to_session: dict[str, str] = {}
        # id (toolu_...) del blocco tool_use prodotto da un round trip -> fingerprint
        # della conversazione in cui è comparso, per il join con PreToolUse/SubagentStart.
        self.tool_use_to_fingerprint: dict[str, str] = {}

    def _state(self, session_id: str) -> SessionState:
        return self.session_state.setdefault(session_id, SessionState())

    def _merge_session(self, synthetic_id: str, real_id: str) -> None:
        """Sostituisce una sessione sintetica con l'id reale scoperto via hook."""
        if synthetic_id == real_id:
            return
        old = self.session_state.pop(synthetic_id, None)
        real = self._state(real_id)
        if old is not None:
            real.turn_index = max(real.turn_index, old.turn_index)
            real.tag = real.tag or old.tag
            real.last_user_text = real.last_user_text or old.last_user_text
            for fp in old.fingerprints:
                self.fingerprint_to_session[fp] = real_id
                real.fingerprints.add(fp)
        for fp, sid in list(self.fingerprint_to_session.items()):
            if sid == synthetic_id:
                self.fingerprint_to_session[fp] = real_id
                real.fingerprints.add(fp)

    # -- round trip (proxy) ---------------------------------------------

    def correlate_round_trip(self, record: dict) -> dict:
        """Assegna session_id/turn_index/agent_id a un round trip del proxy.

        Ritorna {"session_id", "turn_index", "agent_id", "is_new_session", "is_new_turn"}.
        """
        body = (record.get("request") or {}).get("body") or {}
        messages = body.get("messages") or []
        system = body.get("system")
        tag = record.get("tag")

        first_user = next((m for m in messages if m.get("role") == "user"), None)
        fp = fingerprint(system, first_user) if first_user is not None else None

        session_id = self.fingerprint_to_session.get(fp) if fp else None
        is_new_session = False
        if session_id is None:
            session_id = f"syn-{fp[:12]}" if fp else f"syn-unknown-{id(record)}"
            if fp:
                self.fingerprint_to_session[fp] = session_id
            is_new_session = True

        state = self._state(session_id)
        if fp:
            state.fingerprints.add(fp)
        if tag:
            state.tag = tag

        is_new_turn = False
        if not state.has_hooks:
            last_message = messages[-1] if messages else None
            if last_message is not None and last_message.get("role") == "user":
                content = last_message.get("content")
                text = _extract_user_text(content)
                if (
                    text is not None
                    and not _is_tool_result_message(content)
                    and text != state.last_user_text
                ):
                    state.turn_index += 1
                    state.last_user_text = text
                    is_new_turn = True

        # registra i tool_use prodotti in questa risposta per il futuro join
        # con PreToolUse / SubagentStart via tool_use_id.
        message = (record.get("response") or {}).get("message") or {}
        for block in message.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id") and fp:
                self.tool_use_to_fingerprint[block["id"]] = fp

        return {
            "session_id": session_id,
            "turn_index": state.turn_index,
            "agent_id": state.agent_id,
            "is_new_session": is_new_session,
            "is_new_turn": is_new_turn,
        }

    # -- hook events ------------------------------------------------------

    def correlate_hook(self, payload: dict, tag: str | None = None) -> dict:
        """Assegna/aggiorna lo stato di sessione a partire da un evento hook.

        ``payload`` è il JSON dell'hook così come lo manda Claude Code (via
        ``hooks/agentspy_hook.py``): ci si aspetta almeno ``session_id`` e
        ``hook_event_name``. Ritorna {"session_id", "turn_index", "agent_id",
        "parent_session_id", "is_new_turn"}.
        """
        session_id = payload.get("session_id")
        hook_name = payload.get("hook_event_name")
        state = self._state(session_id) if session_id else None
        if state is not None:
            state.has_hooks = True
            if tag:
                state.tag = tag

        is_new_turn = False
        merged_from: list[str] = []

        if hook_name == "PreToolUse" and state is not None:
            tool_use_id = payload.get("tool_use_id") or (payload.get("tool_input") or {}).get(
                "tool_use_id"
            )
            fp = self.tool_use_to_fingerprint.get(tool_use_id) if tool_use_id else None
            if fp:
                synthetic = self.fingerprint_to_session.get(fp)
                if synthetic and synthetic != session_id:
                    self._merge_session(synthetic, session_id)
                    merged_from.append(synthetic)
                self.fingerprint_to_session[fp] = session_id
                state.fingerprints.add(fp)

        elif hook_name == "UserPromptSubmit" and state is not None:
            state.turn_index += 1
            prompt = payload.get("prompt")
            if isinstance(prompt, str):
                state.last_user_text = prompt
            is_new_turn = True

        elif hook_name == "SubagentStart" and state is not None:
            agent_id = payload.get("agent_id") or payload.get("subagent_type")
            parent_session_id = payload.get("parent_session_id")
            if not parent_session_id:
                parent_tool_use_id = payload.get("parent_tool_use_id") or payload.get("tool_use_id")
                parent_fp = (
                    self.tool_use_to_fingerprint.get(parent_tool_use_id)
                    if parent_tool_use_id
                    else None
                )
                parent_session_id = self.fingerprint_to_session.get(parent_fp) if parent_fp else None
            state.agent_id = agent_id
            state.parent_session_id = parent_session_id

        elif hook_name == "SubagentStop" and state is not None:
            pass  # nessuna transizione di stato aggiuntiva: solo ended_at lato store

        return {
            "session_id": session_id,
            "turn_index": state.turn_index if state else None,
            "agent_id": state.agent_id if state else None,
            "parent_session_id": state.parent_session_id if state else None,
            "is_new_turn": is_new_turn,
            # sessioni sintetiche assorbite da questa sessione reale: il
            # chiamante DEVE riassegnarne gli eventi nello store
            # (store.reassign_session) e notificare i client.
            "merged_from": merged_from,
        }
