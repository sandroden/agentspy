"""Transparent proxy towards the LLM upstream: transport only, provider-agnostic.

The forward is parameterized (upstream/client injected) and an ``on_event``
callback is invoked at the end of the round trip with the full record.
Everything that depends on the provider protocol (body analysis, SSE
reconstruction, usage) is delegated to a ``ProviderAdapter`` (see
``providers/``); here only HTTP forwarding, header redaction, timing and record
emission remain. Whoever assembles the app (``app.py``) wires ``on_event`` to
correlate+store+ws.
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

from .providers import ProviderAdapter, get_provider

logger = logging.getLogger(__name__)

TAG_HEADER = "x-agentspy-tag"

# hop-by-hop headers, or ones that must not be forwarded/returned as-is
SKIP_REQ_HEADERS = {"host", "content-length", "accept-encoding", "connection"}
SKIP_RESP_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection"}
# never store these in clear text
SENSITIVE_HEADERS = {"authorization", "x-api-key", "cookie", "proxy-authorization"}

OnEvent = Callable[[dict], Awaitable[None]]


def redact_headers(headers) -> dict:
    return {
        k: ("<redacted>" if k.lower() in SENSITIVE_HEADERS else v)
        for k, v in headers.items()
    }


class ProxyForwarder:
    """Forwards to the upstream any request not handled locally.

    ``on_event`` is called (in the background, without blocking the response to
    the client) with the full round trip record, as soon as it is available.
    """

    def __init__(
        self,
        upstream: str,
        client: httpx.AsyncClient,
        on_event: OnEvent | None = None,
        provider: ProviderAdapter | None = None,
    ):
        self.upstream = upstream.rstrip("/")
        self.client = client
        self.on_event = on_event
        self.provider = provider or get_provider()
        # in-flight emission tasks: we keep a reference because
        # asyncio.create_task does not, and the task could be GC'd halfway.
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
            "provider": self.provider.name,
            "timing": {"ts_start": t_start},
            "request": {
                "headers": redact_headers(request.headers),
                "analysis": (
                    self.provider.analyze_request(body_json)
                    if isinstance(body_json, dict)
                    else {}
                ),
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
            collector = self.provider.stream_collector()

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
                    # The bytes have already been delivered to the client: a
                    # store error must not turn a successful round trip into 500.
                    try:
                        await self._emit(record)
                    except Exception:
                        logger.exception("agentspy: SSE record emission failed")

            return StreamingResponse(
                tee(), status_code=upstream_resp.status_code, headers=resp_headers
            )

        # non-streaming response (count_tokens, errors, etc.)
        data = await upstream_resp.aread()
        await upstream_resp.aclose()
        record["timing"]["ttfb_s"] = round(time.time() - t_start, 3)
        record["timing"]["total_s"] = round(time.time() - t_start, 3)
        try:
            body = json.loads(data)
            record["response"] = {"type": "json", "body": body}
            record["response"].update(self.provider.json_response_summary(body))
        except json.JSONDecodeError:
            record["response"] = {"type": "raw", "body": data.decode("utf-8", "replace")[:2000]}
        # Emission off the critical path: the upstream response is already
        # ready and must neither wait for the DB write nor propagate its errors.
        self._emit_background(record)
        return Response(data, status_code=upstream_resp.status_code, headers=resp_headers)

    def _emit_background(self, record: dict) -> None:
        """Schedule the emission without blocking the response or propagating errors."""
        if self.on_event is None:
            return
        task = asyncio.create_task(self._emit_safe(record))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _emit_safe(self, record: dict) -> None:
        try:
            await self._emit(record)
        except Exception:
            logger.exception("agentspy: non-streaming record emission failed")

    async def _emit(self, record: dict) -> None:
        if self.on_event is not None:
            await self.on_event(record)
