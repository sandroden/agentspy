"""Assigns proxy round trips and hook/mcp events to sessions/turns/subagents.

HTTP traffic towards the Anthropic API carries no session_id: we derive it with
the rules described in `.okf/design/correlation.md`, in order of strength:

1. ``tool_use_id``: the ``PreToolUse`` hook carries ``session_id`` +
   ``tool_use_id``; the previous round trip contained a ``tool_use`` block with
   that id (``toolu_...``) produced by the model: it ties the API conversation
   to the hook session, replacing the synthetic session created so far.
2. ``UserPromptSubmit``: when it arrives, it advances the turn
   (``turn_index += 1``) authoritatively for that session (from then on the
   session has "hooks active" and the user-text heuristic is disabled).
3. **Conversation fingerprint**: sha256 of (serialized system + first user
   message). Later round trips with the same fingerprint (the conversation
   grows: more messages, same prefix) are chained to the same session, even
   without any hook.
4. ``x-agentspy-tag`` header → session tag (round trip) or ``tag`` field of the
   ingest body (hook/mcp).
5. ``SubagentStart``/``SubagentStop`` → child session with
   ``parent_session_id``, attached to the parent via the ``tool_use_id`` of the
   Task/Agent call (same mechanism as point 1) or, if the hook payload already
   provides it explicitly, via ``parent_session_id``.

Known limits (MVP, they degrade without breaking):
* Without any hook, all sessions are synthetic (``syn-<fingerprint[:12]>``)
  and turns are heuristic: a new turn when the last ``user`` message of the
  round trip is textual and is NOT a tool result (``tool_result``), and the
  text differs from the last prompt seen for that session.
* The fingerprint uses system + first user message: two distinct conversations
  with the *same* system prompt and the same very first message (rare but
  possible with identical test prompts) collide in the same synthetic session
  until a hook arrives to disambiguate them.
* The exact schema of Claude Code's hook payloads (field names for
  ``SubagentStart``/``SubagentStop``) has not been verified empirically at this
  stage (F5 will do it with real sessions); here several reasonable field-name
  variants are accepted (``parent_tool_use_id``/``tool_use_id``, explicit
  ``parent_session_id`` if present) to be robust to small schema differences.
* Out-of-order requests (retry/parallelism) are not handled explicitly: the
  turn heuristic can behave unpredictably if round trips reach the collector in
  an order different from the real temporal one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .runtimes import AgentRuntime, get_runtime


def _strip_volatile(obj):
    """Recursively removes the fields that vary between round trips of the same
    conversation: the ``cache_control`` markers move when the cache checkpoint
    advances, and would change the fingerprint of a conversation that is in fact
    the same one."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


def fingerprint(system, first_user_message, session_key: str | None = None) -> str:
    """sha256 of (serialized system + first user message + session
    discriminator), used to chain round trips of the same conversation without
    hooks.

    ``session_key`` is the ``x-claude-code-session-id`` header that Claude Code
    (cli >= 2.x) sends on EVERY request: without it two concurrent runs with the
    same system and the same first prompt (e.g. two test sessions, or the
    "generate title" service traffic, identical across different sessions) would
    collapse into the same synthetic session. Verified empirically: the header is
    stable within a conversation (for real sessions it matches their id) and
    distinct between different runs. When absent (old cli), the fingerprint
    degrades to the previous behaviour (system + first user only)."""
    payload = (
        json.dumps(_strip_volatile(system), sort_keys=True, ensure_ascii=False)
        + "|"
        + json.dumps(_strip_volatile(first_user_message), sort_keys=True, ensure_ascii=False)
        + "|"
        + (session_key or "")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _header_ci(headers: dict | None, name: str) -> str | None:
    """Case-insensitive read of a header from the record (stored headers are
    already lowercase, but we do not take the normalization for granted)."""
    if not headers:
        return None
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target:
            return v
    return None


def fingerprint_inputs(record: dict, session_id_header: str):
    """Extracts (system, first user message, session_key, messages) from a round
    trip record. Shared between live correlation and rehydration from the DB, so
    the fingerprints recomputed at startup match the live ones.

    ``session_id_header`` is the name of the header with which the agent runtime
    marks the session (runtime knowledge, not correlation knowledge)."""
    body = (record.get("request") or {}).get("body") or {}
    messages = body.get("messages") or []
    system = body.get("system")
    first_user = next((m for m in messages if isinstance(m, dict) and m.get("role") == "user"), None)
    headers = (record.get("request") or {}).get("headers")
    session_key = _header_ci(headers, session_id_header)
    return system, first_user, session_key, messages


def _extract_user_text(content) -> str | None:
    """Text of the user message, if present. Concatenates ALL 'text' blocks:
    Claude Code puts system-reminder blocks alongside the user prompt, and the
    first block alone could be identical across different turns."""
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
    """True if the user message is (even only in part) a tool_result: automatic
    continuation of the tool loop, not a new user turn."""
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
    """In-memory correlation state. Pure methods on the passed data, no I/O."""

    def __init__(self, runtime: AgentRuntime | None = None):
        self.runtime = runtime or get_runtime()
        self.session_state: dict[str, SessionState] = {}
        self.fingerprint_to_session: dict[str, str] = {}
        # id (toolu_...) of the tool_use block produced by a round trip -> fingerprint
        # of the conversation it appeared in, for the join with PreToolUse/SubagentStart.
        self.tool_use_to_fingerprint: dict[str, str] = {}
        # textual prompt of UserPromptSubmit -> LIST of real session_ids that sent
        # it: it allows tying conversations WITHOUT tool calls (which have no
        # tool_use_id to join on) to their session_id, by comparing the last user
        # message. It is a list (not a single id) because two concurrent runs can
        # send the very same prompt: the matching picks the right run with the
        # session_key from the header, without one overwriting the other.
        self.prompt_to_sessions: dict[str, list[str]] = {}

    def _remember_prompt(self, prompt: str, session_id: str) -> None:
        lst = self.prompt_to_sessions.setdefault(prompt, [])
        if session_id not in lst:
            lst.append(session_id)
        # global ceiling on the number of remembered (prompt, session) pairs
        total = sum(len(v) for v in self.prompt_to_sessions.values())
        while total > 200 and self.prompt_to_sessions:
            oldest = next(iter(self.prompt_to_sessions))
            self.prompt_to_sessions[oldest].pop(0)
            if not self.prompt_to_sessions[oldest]:
                del self.prompt_to_sessions[oldest]
            total -= 1

    def _match_pending_prompt(self, content, preferred_session_id: str | None = None) -> str | None:
        """Looks among the prompts registered by UserPromptSubmit for one that
        matches a text block of the user message (Claude Code puts
        system-reminder blocks alongside the prompt: the comparison is per single
        block).

        If several runs sent the same prompt, ``preferred_session_id`` (the
        session_key from the round trip header, which for real sessions matches
        their id) selects the correct run; otherwise the oldest pending one is
        taken (FIFO)."""
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

    def rehydrate(self, sessions: list[dict], events: list[dict]) -> None:
        """Rebuilds the in-memory state from a DB snapshot (best-effort).

        On restart the Correlator would start empty: turn_index from 1 (round
        trips renumbered and overlapping), round trips without hooks creating new
        syn-, MCP/subagent joins (tool_use_id) lost. Here the essentials are
        restored from the events already saved: session ids are the DEFINITIVE
        ones (post merge) from the DB, so the recomputed fingerprints already
        point to the right session. ``events`` is expected ordered by ts_start."""
        for s in sessions:
            st = self._state(s["id"])
            st.tag = st.tag or s.get("tag")
            st.agent_id = st.agent_id or s.get("agent_id")
            st.parent_session_id = st.parent_session_id or s.get("parent_session_id")

        for e in events:
            sid = e.get("session_id")
            if not sid:
                continue
            st = self._state(sid)
            ti = e.get("turn_index")
            if isinstance(ti, int):
                st.turn_index = max(st.turn_index, ti)
            payload = e.get("payload") or {}
            if e.get("kind") == "hook":
                st.has_hooks = True
                if e.get("subkind") == self.runtime.hook_user_prompt:
                    prompt = payload.get("prompt")
                    if isinstance(prompt, str):
                        st.last_user_text = prompt
                        self._remember_prompt(prompt, sid)
            elif e.get("kind") == "round_trip":
                system, first_user, session_key, _ = fingerprint_inputs(
                    payload, self.runtime.session_id_header
                )
                if first_user is None:
                    continue
                fp = fingerprint(system, first_user, session_key)
                self.fingerprint_to_session[fp] = sid
                st.fingerprints.add(fp)
                message = (payload.get("response") or {}).get("message") or {}
                for block in message.get("content", []) or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                        self.tool_use_to_fingerprint[block["id"]] = fp

    def session_for_tool_use(self, tool_use_id: str | None) -> str | None:
        """Session of the conversation in which a tool_use appeared.

        Used to tie MCP events to the session: Claude Code passes the tool_use id
        in the params._meta["claudecode/toolUseId"] field of the JSON-RPC
        tools/call."""
        if not tool_use_id:
            return None
        fp = self.tool_use_to_fingerprint.get(tool_use_id)
        return self.fingerprint_to_session.get(fp) if fp else None

    def _merge_session(self, synthetic_id: str, real_id: str) -> None:
        """Replaces a synthetic session with the real id discovered via hook."""
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
        """Assigns session_id/turn_index/agent_id to a proxy round trip.

        Returns {"session_id", "turn_index", "agent_id", "is_new_session", "is_new_turn"}.
        """
        system, first_user, session_key, messages = fingerprint_inputs(
            record, self.runtime.session_id_header
        )
        tag = record.get("tag")

        fp = fingerprint(system, first_user, session_key) if first_user is not None else None

        session_id = self.fingerprint_to_session.get(fp) if fp else None
        is_new_session = False
        if session_id is None:
            session_id = f"syn-{fp[:12]}" if fp else f"syn-unknown-{id(record)}"
            if fp:
                self.fingerprint_to_session[fp] = session_id
            is_new_session = True

        # binding via prompt (rule 2): a still-synthetic conversation whose last
        # user message matches a prompt announced by UserPromptSubmit belongs to
        # that real session. It covers conversations without tool calls, where
        # the join by tool_use_id will never fire.
        merged_from: list[str] = []
        if session_id.startswith("syn-") and messages:
            last_message = self.runtime.last_user_message(messages)
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

        # Attachment to the parent session via the x-claude-code-session-id
        # header (claude-cli >= 2.x sends it on every request). It does NOT
        # replace correlation by fingerprint: subagent conversations carry the
        # PARENT's id and must be able to migrate into the child session on the
        # first PreToolUse (the merge only fires on a "syn-" owner). Here the
        # synthetic is only nested under the parent, so service traffic is not
        # left orphaned at the top of the sidebar. Only if the parent is already
        # known via hook: the sidebar hides the children of sessions that do not
        # exist as a row in the DB.
        if session_id.startswith("syn-") and state.parent_session_id is None:
            mother = self.session_state.get(session_key) if session_key else None
            if mother is not None and mother.has_hooks:
                state.parent_session_id = session_key

        is_new_turn = False
        if not state.has_hooks:
            last_message = self.runtime.last_user_message(messages) if messages else None
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

        # register the tool_use blocks produced in this response for the future
        # join with PreToolUse / SubagentStart via tool_use_id.
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
        """Assigns/updates the session state starting from a hook event.

        ``payload`` is the hook JSON exactly as Claude Code sends it (via
        ``hooks/agentspy_hook.py``): at least ``session_id`` and
        ``hook_event_name`` are expected. Returns {"session_id", "turn_index",
        "agent_id", "parent_session_id", "is_new_turn"}.
        """
        session_id = payload.get("session_id")
        hook_name = payload.get("hook_event_name")
        agent_id = payload.get("agent_id")
        state = self._state(session_id) if session_id else None
        if state is not None:
            state.has_hooks = True
            if tag:
                state.tag = tag

        # Real schema (verified in F5): hooks generated INSIDE a subagent carry
        # agent_id/agent_type but the PARENT's session_id. The event therefore
        # belongs to the child session "sub-<agent_id>"; SubagentStart/Stop stay
        # instead as markers on the parent's timeline.
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
            if not self.runtime.is_subagent_hook(hook_name):
                target_id, target = child_id, child

        is_new_turn = False
        merged_from: list[str] = []

        if hook_name == self.runtime.hook_pre_tool_use and target is not None:
            tool_use_id = payload.get("tool_use_id")
            fp = self.tool_use_to_fingerprint.get(tool_use_id) if tool_use_id else None
            if fp:
                owner = self.fingerprint_to_session.get(fp)
                if owner and owner != target_id and owner.startswith("syn-"):
                    self._merge_session(owner, target_id)
                    merged_from.append(owner)
                self.fingerprint_to_session[fp] = target_id
                target.fingerprints.add(fp)

        elif hook_name == self.runtime.hook_user_prompt and state is not None:
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
            # absorbed synthetic sessions: the caller MUST reassign their events
            # (store.reassign_session) and notify the clients.
            "merged_from": merged_from,
            # child session discovered/updated by this hook: the caller upserts
            # it into the store (with live=False on SubagentStop).
            "child_session": child_session,
            "child_ended": bool(agent_id) and hook_name == self.runtime.hook_subagent_stop,
        }
