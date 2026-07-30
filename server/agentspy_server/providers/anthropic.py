"""Adapter for the Anthropic Messages API (agentspy's "native" provider).

agentspy's neutral model derives from this API, so here the translation is
almost the identity: the real work is reconstructing the message from the SSE
stream and the discipline on usage (see ``_PROMPT_USAGE_KEYS``).
"""

from __future__ import annotations

import json

from .base import ProviderAdapter, StreamCollector


def jsize(obj) -> int:
    """Size in characters of the JSON serialization (rough proxy for tokens)."""
    return len(json.dumps(obj, ensure_ascii=False))


def analyze_request_body(body: dict) -> dict:
    """Breaks the request down into its parts: system, tools, messages."""
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


# The prompt tokens (input, cache read/creation) are fixed when the request
# starts: message_start reports them correctly and they represent the real
# occupancy of the context window. On turns with extended/interleaved thinking,
# message_delta reports a cumulative value (cache-read *throughput*: the prompt
# re-read several times during the turn), which is NOT the occupancy and would
# inflate the gauge. The prompt fields are therefore frozen by message_start and
# NEVER accepted from message_delta; from message_delta we only take the output
# (output_tokens, which grows during streaming).
_PROMPT_USAGE_KEYS = frozenset(
    {"input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "cache_creation"}
)


class SSECollector(StreamCollector):
    """Reconstructs the assistant message from the SSE events and extracts usage/timing."""

    def __init__(self):
        self.events_count: dict = {}
        self.message: dict = {}
        self.usage: dict = {}
        self.stop_reason = None
        self.blocks: list = []
        self.error = None
        self._buf = ""
        # True if message_start reported at least one prompt token: from there
        # on the prompt fields are frozen (see _merge_usage).
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
        """Merges a usage into the accumulated state preserving the prompt tokens.

        If message_start reported prompt tokens (the real Anthropic API always
        does), the fields in _PROMPT_USAGE_KEYS stay frozen at that value:
        message_delta may report a cumulative value (throughput) that skews the
        occupancy of the context window, so there they are ignored — also for
        the keys message_start may have omitted (e.g.
        cache_creation_input_tokens): the delta's inflated value must not get in
        anyway.

        Some Anthropic-compatible emulations (OpenRouter) instead send
        message_start with usage at zero and the real values only in
        message_delta: if NO prompt token arrived from the start, the delta is
        the only source and is accepted.
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
        # An error event mid-stream (after message_start) leaves stop_reason at
        # None and the HTTP request stays 200: without this the round trip would
        # look successful. stop_reason="error" makes it visible downstream
        # (app.py persists it), while the detail stays in result["error"].
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
        # A body with "messages" is not enough: /v1/messages/count_tokens has it
        # too (Claude Code makes dozens at startup, one per agent/skill, each
        # with a different fingerprint -> avalanche of synthetic sessions), so
        # the path is filtered as well.
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
        # `cache_creation` reports the TTL with which the tokens just written
        # were cached (5 minutes or 1 hour). The tier is NOT a cosmetic detail:
        # the 1h write costs 2x the input, the 5m one 1.25x, so without the
        # split the cache cost is underestimated. Absent on Anthropic-compatible
        # providers that do not expose it -> None (not 0): downstream "unknown
        # tier" and "zero tokens written in that tier" stay distinct.
        creation = usage.get("cache_creation")
        creation = creation if isinstance(creation, dict) else {}
        return {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_read_tokens": usage.get("cache_read_input_tokens"),
            "cache_write_tokens": usage.get("cache_creation_input_tokens"),
            "cache_write_5m_tokens": creation.get("ephemeral_5m_input_tokens"),
            "cache_write_1h_tokens": creation.get("ephemeral_1h_input_tokens"),
        }
