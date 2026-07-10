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


def fingerprint(system, first_user_message, session_key: str | None = None) -> str:
    """sha256 di (system serializzato + primo messaggio user + discriminante di
    sessione), usato per incatenare round trip della stessa conversazione senza
    hook.

    ``session_key`` è l'header ``x-claude-code-session-id`` che Claude Code
    (cli >= 2.x) manda su OGNI richiesta: senza di esso due run concorrenti con
    lo stesso system e lo stesso primo prompt (es. due sessioni di test, o il
    traffico di servizio "genera titolo" identico fra sessioni diverse)
    collasserebbero nella stessa sessione sintetica. Verificato empiricamente:
    l'header è stabile entro una conversazione (per le sessioni reali coincide
    con il loro id) e distinto fra run diversi. Quando assente (cli vecchia), il
    fingerprint degrada al comportamento precedente (solo system + primo user)."""
    payload = (
        json.dumps(_strip_volatile(system), sort_keys=True, ensure_ascii=False)
        + "|"
        + json.dumps(_strip_volatile(first_user_message), sort_keys=True, ensure_ascii=False)
        + "|"
        + (session_key or "")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _header_ci(headers: dict | None, name: str) -> str | None:
    """Lettura case-insensitive di un header dal record (gli header salvati sono
    già in minuscolo, ma non diamo per scontata la normalizzazione)."""
    if not headers:
        return None
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target:
            return v
    return None


def fingerprint_inputs(record: dict):
    """Estrae (system, primo messaggio user, session_key, messages) da un record
    di round trip. Condiviso fra la correlazione live e la reidratazione dal DB,
    così i fingerprint ricalcolati all'avvio combaciano con quelli vivi."""
    body = (record.get("request") or {}).get("body") or {}
    messages = body.get("messages") or []
    system = body.get("system")
    first_user = next((m for m in messages if isinstance(m, dict) and m.get("role") == "user"), None)
    headers = (record.get("request") or {}).get("headers")
    session_key = _header_ci(headers, "x-claude-code-session-id")
    return system, first_user, session_key, messages


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


def _last_user_message(messages) -> dict | None:
    """Ultimo messaggio con role='user'. NON basta messages[-1]: Claude Code
    (cli >= 2.1) accoda alla richiesta un messaggio con role='system' (es. il
    reminder dei deferred tools), che maschererebbe il prompt dell'utente sia
    al binding via prompt sia all'euristica del turno."""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            return m
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
        # prompt testuale di UserPromptSubmit -> LISTA di session_id reali che lo
        # hanno inviato: permette di legare conversazioni SENZA tool call (che non
        # hanno tool_use_id da joinare) al loro session_id, confrontando l'ultimo
        # messaggio user. È una lista (non un singolo id) perché due run concorrenti
        # possono inviare lo stesso identico prompt: il matching sceglie la run
        # giusta col session_key dell'header, senza che l'una sovrascriva l'altra.
        self.prompt_to_sessions: dict[str, list[str]] = {}

    def _remember_prompt(self, prompt: str, session_id: str) -> None:
        lst = self.prompt_to_sessions.setdefault(prompt, [])
        if session_id not in lst:
            lst.append(session_id)
        # tetto globale sul numero di (prompt, sessione) ricordati
        total = sum(len(v) for v in self.prompt_to_sessions.values())
        while total > 200 and self.prompt_to_sessions:
            oldest = next(iter(self.prompt_to_sessions))
            self.prompt_to_sessions[oldest].pop(0)
            if not self.prompt_to_sessions[oldest]:
                del self.prompt_to_sessions[oldest]
            total -= 1

    def _match_pending_prompt(self, content, preferred_session_id: str | None = None) -> str | None:
        """Cerca fra i prompt registrati da UserPromptSubmit uno che coincida
        con un blocco text del messaggio user (Claude Code affianca al prompt
        blocchi di system-reminder: il confronto è per singolo blocco).

        Se più run hanno inviato lo stesso prompt, ``preferred_session_id`` (il
        session_key dell'header del round trip, che per le sessioni reali coincide
        col loro id) seleziona la run corretta; altrimenti si prende la più
        vecchia in attesa (FIFO)."""
        texts: list[str] = []
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.extend(
                b.get("text") or ""
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        for t in texts:
            for key in (t, t.strip()):
                lst = self.prompt_to_sessions.get(key)
                if not lst:
                    continue
                if preferred_session_id and preferred_session_id in lst:
                    lst.remove(preferred_session_id)
                    sid = preferred_session_id
                else:
                    sid = lst.pop(0)
                if not lst:
                    del self.prompt_to_sessions[key]
                return sid
        return None

    def _state(self, session_id: str) -> SessionState:
        return self.session_state.setdefault(session_id, SessionState())

    def session_for_tool_use(self, tool_use_id: str | None) -> str | None:
        """Sessione della conversazione in cui è comparso un tool_use.

        Usato per legare gli eventi MCP alla sessione: Claude Code passa il
        tool_use id nel campo params._meta["claudecode/toolUseId"] della
        tools/call JSON-RPC."""
        if not tool_use_id:
            return None
        fp = self.tool_use_to_fingerprint.get(tool_use_id)
        return self.fingerprint_to_session.get(fp) if fp else None

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
        system, first_user, session_key, messages = fingerprint_inputs(record)
        tag = record.get("tag")

        fp = fingerprint(system, first_user, session_key) if first_user is not None else None

        session_id = self.fingerprint_to_session.get(fp) if fp else None
        is_new_session = False
        if session_id is None:
            session_id = f"syn-{fp[:12]}" if fp else f"syn-unknown-{id(record)}"
            if fp:
                self.fingerprint_to_session[fp] = session_id
            is_new_session = True

        # binding via prompt (regola 2): una conversazione ancora sintetica il
        # cui ultimo messaggio user coincide con un prompt annunciato da
        # UserPromptSubmit appartiene a quella sessione reale. Copre le
        # conversazioni senza tool call, dove il join per tool_use_id non
        # scatterà mai.
        merged_from: list[str] = []
        if session_id.startswith("syn-") and messages:
            last_message = _last_user_message(messages)
            if last_message is not None:
                real_sid = self._match_pending_prompt(last_message.get("content"), session_key)
                if real_sid:
                    if not is_new_session:
                        merged_from.append(session_id)
                    self._merge_session(session_id, real_sid)
                    if fp:
                        self.fingerprint_to_session[fp] = real_sid
                    session_id = real_sid
                    is_new_session = False

        state = self._state(session_id)
        if fp:
            state.fingerprints.add(fp)
        if tag:
            state.tag = tag

        # Aggancio alla sessione madre via header x-claude-code-session-id
        # (claude-cli >= 2.x lo manda su ogni richiesta). NON sostituisce la
        # correlazione per fingerprint: le conversazioni dei subagenti portano
        # l'id della MADRE e devono poter migrare nella sessione figlia al
        # primo PreToolUse (il merge scatta solo su owner "syn-"). Qui la
        # sintetica viene solo nidificata sotto la madre, così il traffico di
        # servizio non resta orfano in cima alla sidebar. Solo se la madre è
        # già nota via hook: la sidebar nasconde i figli di sessioni che non
        # esistono come riga nel DB.
        if session_id.startswith("syn-") and state.parent_session_id is None:
            mother = self.session_state.get(session_key) if session_key else None
            if mother is not None and mother.has_hooks:
                state.parent_session_id = session_key

        is_new_turn = False
        if not state.has_hooks:
            last_message = _last_user_message(messages) if messages else None
            if last_message is not None:
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
            "parent_session_id": state.parent_session_id,
            "is_new_session": is_new_session,
            "is_new_turn": is_new_turn,
            "merged_from": merged_from,
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
        agent_id = payload.get("agent_id")
        state = self._state(session_id) if session_id else None
        if state is not None:
            state.has_hooks = True
            if tag:
                state.tag = tag

        # Schema reale (verificato in F5): gli hook generati DENTRO un
        # subagente portano agent_id/agent_type ma il session_id della MADRE.
        # L'evento appartiene quindi alla sessione figlia "sub-<agent_id>";
        # SubagentStart/Stop restano invece marker sulla timeline della madre.
        child_session = None
        target_id, target = session_id, state
        if agent_id and session_id:
            child_id = f"sub-{agent_id}"
            child = self._state(child_id)
            child.has_hooks = True
            child.agent_id = agent_id
            child.parent_session_id = session_id
            if tag:
                child.tag = tag
            child_session = {
                "id": child_id,
                "agent_id": agent_id,
                "agent_type": payload.get("agent_type"),
                "parent_session_id": session_id,
            }
            if hook_name not in ("SubagentStart", "SubagentStop"):
                target_id, target = child_id, child

        is_new_turn = False
        merged_from: list[str] = []

        if hook_name == "PreToolUse" and target is not None:
            tool_use_id = payload.get("tool_use_id")
            fp = self.tool_use_to_fingerprint.get(tool_use_id) if tool_use_id else None
            if fp:
                owner = self.fingerprint_to_session.get(fp)
                if owner and owner != target_id and owner.startswith("syn-"):
                    self._merge_session(owner, target_id)
                    merged_from.append(owner)
                self.fingerprint_to_session[fp] = target_id
                target.fingerprints.add(fp)

        elif hook_name == "UserPromptSubmit" and state is not None:
            state.turn_index += 1
            prompt = payload.get("prompt")
            if isinstance(prompt, str):
                state.last_user_text = prompt
                if session_id:
                    self._remember_prompt(prompt, session_id)
            is_new_turn = True

        return {
            "session_id": target_id,
            "turn_index": target.turn_index if target else None,
            "agent_id": target.agent_id if target else None,
            "parent_session_id": target.parent_session_id if target else None,
            "is_new_turn": is_new_turn,
            # sessioni sintetiche assorbite: il chiamante DEVE riassegnarne
            # gli eventi (store.reassign_session) e notificare i client.
            "merged_from": merged_from,
            # sessione figlia scoperta/aggiornata da questo hook: il chiamante
            # la upserta nello store (con live=False su SubagentStop).
            "child_session": child_session,
            "child_ended": bool(agent_id) and hook_name == "SubagentStop",
        }
