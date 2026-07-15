"""Adapter per l'API Anthropic Messages (il provider "nativo" di agentspy).

Il modello neutro di agentspy deriva da questa API, quindi qui la traduzione
è quasi l'identità: il lavoro vero è la ricostruzione del messaggio dallo
stream SSE e la disciplina sull'usage (vedi ``_PROMPT_USAGE_KEYS``).
"""

from __future__ import annotations

import json

from .base import ProviderAdapter, StreamCollector


def jsize(obj) -> int:
    """Dimensione in caratteri della serializzazione JSON (proxy grezzo dei token)."""
    return len(json.dumps(obj, ensure_ascii=False))


def analyze_request_body(body: dict) -> dict:
    """Scompone la richiesta nelle sue parti: system, tools, messages."""
    info: dict = {
        "model": body.get("model"),
        "stream": body.get("stream", False),
        "max_tokens": body.get("max_tokens"),
    }
    system = body.get("system")
    if system is not None:
        info["system_chars"] = len(system) if isinstance(system, str) else jsize(system)
    tools = body.get("tools")
    if tools:
        info["tools"] = {
            "count": len(tools),
            "chars": jsize(tools),
            "names": [t.get("name", t.get("type", "?")) for t in tools],
        }
    messages = body.get("messages")
    if messages is not None:
        roles: dict = {}
        for m in messages:
            roles[m.get("role", "?")] = roles.get(m.get("role", "?"), 0) + 1
        info["messages"] = {
            "count": len(messages),
            "chars": jsize(messages),
            "roles": roles,
        }
    return info


# I token del prompt (input, cache read/creation) sono fissati quando la
# richiesta parte: message_start li riporta corretti e rappresentano l'occupancy
# reale della finestra di contesto. Su turni con extended/interleaved thinking,
# message_delta ne riporta un cumulativo (cache-read *throughput*: il prompt
# riletto più volte durante il turno), che NON è l'occupancy e gonfierebbe il
# gauge. I campi di prompt vengono quindi congelati da message_start e MAI
# accettati da message_delta; da message_delta prendiamo solo l'output
# (output_tokens, che cresce durante lo streaming).
_PROMPT_USAGE_KEYS = frozenset(
    {"input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "cache_creation"}
)


class SSECollector(StreamCollector):
    """Ricostruisce il messaggio assistant dagli eventi SSE e ne estrae usage/timing."""

    def __init__(self):
        self.events_count: dict = {}
        self.message: dict = {}
        self.usage: dict = {}
        self.stop_reason = None
        self.blocks: list = []
        self.error = None
        self._buf = ""
        # True se message_start ha riportato almeno un token di prompt: da lì
        # in poi i campi di prompt sono congelati (vedi _merge_usage).
        self._prompt_from_start = False

    def feed(self, chunk: bytes) -> None:
        self._buf += chunk.decode("utf-8", errors="replace")
        while "\n\n" in self._buf:
            block, self._buf = self._buf.split("\n\n", 1)
            self._handle_event(block)

    def _handle_event(self, block: str) -> None:
        event_type, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if not event_type or data is None:
            return
        self.events_count[event_type] = self.events_count.get(event_type, 0) + 1
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return

        if event_type == "message_start":
            msg = payload.get("message", {})
            self.message = {k: v for k, v in msg.items() if k != "content"}
            self._merge_usage(msg.get("usage", {}), from_start=True)
        elif event_type == "content_block_start":
            block_data = dict(payload.get("content_block", {}))
            block_data.setdefault("text", "")
            block_data["_partial_json"] = ""
            self.blocks.append(block_data)
        elif event_type == "content_block_delta":
            delta = payload.get("delta", {})
            idx = payload.get("index", len(self.blocks) - 1)
            if 0 <= idx < len(self.blocks):
                b = self.blocks[idx]
                kind = delta.get("type")
                if kind == "text_delta":
                    b["text"] += delta.get("text", "")
                elif kind == "input_json_delta":
                    b["_partial_json"] += delta.get("partial_json", "")
                elif kind == "thinking_delta":
                    b["thinking"] = b.get("thinking", "") + delta.get("thinking", "")
        elif event_type == "message_delta":
            self._merge_usage(payload.get("usage", {}))
            self.stop_reason = payload.get("delta", {}).get("stop_reason")
        elif event_type == "error":
            self.error = payload

    def _merge_usage(self, new: dict, *, from_start: bool = False) -> None:
        """Fonde una usage nello stato accumulato preservando i token di prompt.

        Se message_start ha riportato dei token di prompt (l'API Anthropic vera
        lo fa sempre), i campi in _PROMPT_USAGE_KEYS restano congelati a quel
        valore: message_delta può riportarne un cumulativo (throughput) che
        falsa l'occupancy della finestra di contesto, quindi lì vengono
        ignorati — anche per le chiavi che message_start avesse omesso (es.
        cache_creation_input_tokens): il valore gonfiato del delta non deve
        comunque entrare.

        Alcune emulazioni Anthropic-compatibili (OpenRouter) invece mandano
        message_start con usage a zero e i valori veri solo in message_delta:
        se dallo start non è arrivato NESSUN token di prompt, il delta è
        l'unica fonte e viene accettato.
        """
        if from_start:
            self._prompt_from_start = any(
                new.get(k) for k in _PROMPT_USAGE_KEYS if isinstance(new.get(k), (int, float))
            )
        for key, value in new.items():
            if key in _PROMPT_USAGE_KEYS and not from_start and self._prompt_from_start:
                continue
            self.usage[key] = value

    def finalize(self) -> dict:
        content = []
        for b in self.blocks:
            b = dict(b)
            pj = b.pop("_partial_json", "")
            if pj:
                try:
                    b["input"] = json.loads(pj)
                except json.JSONDecodeError:
                    b["input_raw"] = pj
            if not b.get("text"):
                b.pop("text", None)
            content.append(b)
        # Un event error a metà stream (dopo message_start) lascia stop_reason
        # a None e la richiesta HTTP resta 200: senza questo il round trip
        # sembrerebbe riuscito. stop_reason="error" lo rende visibile a valle
        # (app.py lo persiste), mentre il dettaglio resta in result["error"].
        stop_reason = self.stop_reason
        if stop_reason is None and self.error is not None:
            stop_reason = "error"
        result = {
            "type": "sse",
            "message": {**self.message, "content": content},
            "usage": self.usage,
            "stop_reason": stop_reason,
            "events_count": self.events_count,
        }
        if self.error:
            result["error"] = self.error
        return result


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"

    def is_model_call(self, path: str, body: dict | None) -> bool:
        # Il body con "messages" non basta: anche /v1/messages/count_tokens lo
        # ha (Claude Code all'avvio ne fa decine, una per agente/skill, ognuna
        # con fingerprint diverso -> valanga di sessioni sintetiche), quindi
        # si filtra anche sul path.
        path = (path or "").rstrip("/")
        return bool(isinstance(body, dict) and body.get("messages") and path.endswith("/messages"))

    def analyze_request(self, body: dict) -> dict:
        return analyze_request_body(body)

    def stream_collector(self) -> SSECollector:
        return SSECollector()

    def json_response_summary(self, body: dict) -> dict:
        if isinstance(body, dict) and body.get("usage"):
            return {"usage": body["usage"], "stop_reason": body.get("stop_reason")}
        return {}

    def normalize_usage(self, usage: dict) -> dict:
        return {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_read_tokens": usage.get("cache_read_input_tokens"),
            "cache_write_tokens": usage.get("cache_creation_input_tokens"),
        }
