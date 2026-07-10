"""Proxy trasparente verso l'API Anthropic.

Evoluzione di ``agentspy_proxy.py`` (root del repo): stessa logica di forward
e ricostruzione SSE, ma parametrizzata (upstream/client iniettati) e con un
callback ``on_event`` invocato a fine round trip invece di scrivere su file.
Chi assembla l'app (``app.py``) collega ``on_event`` a correlate+store+ws.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)

TAG_HEADER = "x-agentspy-tag"

# header hop-by-hop o che non vanno inoltrati/ritornati tal quali
SKIP_REQ_HEADERS = {"host", "content-length", "accept-encoding", "connection"}
SKIP_RESP_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection"}
# non salvare mai questi in chiaro
SENSITIVE_HEADERS = {"authorization", "x-api-key", "cookie", "proxy-authorization"}

OnEvent = Callable[[dict], Awaitable[None]]


def redact_headers(headers) -> dict:
    return {
        k: ("<redacted>" if k.lower() in SENSITIVE_HEADERS else v)
        for k, v in headers.items()
    }


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


class SSECollector:
    """Ricostruisce il messaggio assistant dagli eventi SSE e ne estrae usage/timing."""

    def __init__(self):
        self.events_count: dict = {}
        self.message: dict = {}
        self.usage: dict = {}
        self.stop_reason = None
        self.blocks: list = []
        self.error = None
        self._buf = ""

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

        I campi in _PROMPT_USAGE_KEYS vengono accettati SOLO dallo snapshot di
        message_start (``from_start=True``): message_delta può riportarne un
        cumulativo (throughput) che falsa l'occupancy della finestra di
        contesto, quindi lì vengono sempre ignorati. Guardare ``from_start``
        anziché la mera presenza in ``self.usage`` copre anche il caso in cui
        message_start ometta una chiave (es. cache_creation_input_tokens): il
        valore gonfiato del delta non deve comunque entrare.
        """
        for key, value in new.items():
            if key in _PROMPT_USAGE_KEYS and not from_start:
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


class ProxyForwarder:
    """Inoltra qualunque richiesta non gestita localmente all'upstream Anthropic.

    ``on_event`` viene chiamato (in background, senza bloccare la risposta al
    client) con il record completo del round trip, non appena disponibile.
    """

    def __init__(self, upstream: str, client: httpx.AsyncClient, on_event: OnEvent | None = None):
        self.upstream = upstream.rstrip("/")
        self.client = client
        self.on_event = on_event
        # task di emissione in volo: manteniamo un riferimento perché
        # asyncio.create_task non lo fa e il task potrebbe essere GC'd a metà.
        self._pending: set[asyncio.Task] = set()

    async def forward(self, request: Request) -> Response:
        t_start = time.time()
        raw_body = await request.body()
        try:
            body_json = json.loads(raw_body) if raw_body else None
        except json.JSONDecodeError:
            body_json = None

        tag = request.headers.get(TAG_HEADER)

        record: dict = {
            "method": request.method,
            "path": request.url.path,
            "query": str(request.url.query) if request.url.query else None,
            "tag": tag,
            "timing": {"ts_start": t_start},
            "request": {
                "headers": redact_headers(request.headers),
                "analysis": analyze_request_body(body_json) if isinstance(body_json, dict) else {},
                "body": body_json if body_json is not None else raw_body.decode("utf-8", "replace")[:2000],
            },
        }

        upstream_headers = {
            k: v for k, v in request.headers.items() if k.lower() not in SKIP_REQ_HEADERS
        }
        upstream_headers["accept-encoding"] = "identity"
        url = self.upstream + request.url.path
        if request.url.query:
            url += "?" + request.url.query

        upstream_req = self.client.build_request(
            request.method, url, headers=upstream_headers, content=raw_body
        )
        try:
            upstream_resp = await self.client.send(upstream_req, stream=True)
        except httpx.HTTPError as exc:
            record["status"] = None
            record["response"] = {"error": f"upstream error: {exc!r}"}
            record["timing"]["total_s"] = round(time.time() - t_start, 3)
            await self._emit(record)
            return Response(f"agentspy: upstream error: {exc}", status_code=502)

        record["status"] = upstream_resp.status_code
        resp_headers = {
            k: v for k, v in upstream_resp.headers.items() if k.lower() not in SKIP_RESP_HEADERS
        }
        content_type = upstream_resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            collector = SSECollector()

            async def tee():
                first = True
                try:
                    async for chunk in upstream_resp.aiter_bytes():
                        if first:
                            record["timing"]["ttfb_s"] = round(time.time() - t_start, 3)
                            first = False
                        collector.feed(chunk)
                        yield chunk
                finally:
                    await upstream_resp.aclose()
                    record["timing"]["total_s"] = round(time.time() - t_start, 3)
                    record["response"] = collector.finalize()
                    # I byte sono già stati consegnati al client: un errore di
                    # store non deve trasformare un round trip riuscito in 500.
                    try:
                        await self._emit(record)
                    except Exception:
                        logger.exception("agentspy: emissione record SSE fallita")

            return StreamingResponse(
                tee(), status_code=upstream_resp.status_code, headers=resp_headers
            )

        # risposta non in streaming (count_tokens, errori, ecc.)
        data = await upstream_resp.aread()
        await upstream_resp.aclose()
        record["timing"]["ttfb_s"] = round(time.time() - t_start, 3)
        record["timing"]["total_s"] = round(time.time() - t_start, 3)
        try:
            body = json.loads(data)
            record["response"] = {"type": "json", "body": body}
            if isinstance(body, dict) and body.get("usage"):
                record["response"]["usage"] = body["usage"]
                record["response"]["stop_reason"] = body.get("stop_reason")
        except json.JSONDecodeError:
            record["response"] = {"type": "raw", "body": data.decode("utf-8", "replace")[:2000]}
        # Emissione fuori dal percorso critico: la risposta upstream è già
        # pronta e non deve né attendere la scrittura DB né propagarne gli errori.
        self._emit_background(record)
        return Response(data, status_code=upstream_resp.status_code, headers=resp_headers)

    def _emit_background(self, record: dict) -> None:
        """Pianifica l'emissione senza bloccare la risposta né propagare errori."""
        if self.on_event is None:
            return
        task = asyncio.create_task(self._emit_safe(record))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _emit_safe(self, record: dict) -> None:
        try:
            await self._emit(record)
        except Exception:
            logger.exception("agentspy: emissione record non-streaming fallita")

    async def _emit(self, record: dict) -> None:
        if self.on_event is not None:
            await self.on_event(record)
