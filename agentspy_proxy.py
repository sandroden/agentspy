#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "starlette>=0.37",
#     "uvicorn>=0.30",
#     "httpx>=0.27",
# ]
# ///
"""agentspy — proxy trasparente per spiare il traffico Claude Code <-> API Anthropic.

Uso:
    ./agentspy_proxy.py                      # ascolta su 127.0.0.1:8082
    ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude

Ogni round trip (richiesta POST /v1/messages e relativa risposta, anche in
streaming SSE) viene:
  * inoltrato tal quale all'upstream (default https://api.anthropic.com)
  * riassunto su stdout in tempo reale (una riga per round trip)
  * salvato integralmente in logs/run-<timestamp>.jsonl (un record JSON per riga,
    con il body completo della richiesta: system prompt, tools, messages)

Variabili d'ambiente:
    AGENTSPY_PORT       porta di ascolto (default 8082)
    AGENTSPY_UPSTREAM   base URL upstream (default https://api.anthropic.com)
    AGENTSPY_LOG_DIR    directory dei log (default ./logs accanto allo script)
    AGENTSPY_SAVE_RAW   se "1", salva anche tutti gli eventi SSE grezzi
"""

import json
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

UPSTREAM = os.environ.get("AGENTSPY_UPSTREAM", "https://api.anthropic.com")
PORT = int(os.environ.get("AGENTSPY_PORT", "8082"))
LOG_DIR = Path(os.environ.get("AGENTSPY_LOG_DIR", Path(__file__).parent / "logs"))
SAVE_RAW = os.environ.get("AGENTSPY_SAVE_RAW") == "1"

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"run-{datetime.now():%Y%m%d-%H%M%S}.jsonl"

# header hop-by-hop o che non vanno inoltrati/ritornati tal quali
SKIP_REQ_HEADERS = {"host", "content-length", "accept-encoding", "connection"}
SKIP_RESP_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection"}
SENSITIVE_HEADERS = {"authorization", "x-api-key", "cookie", "proxy-authorization"}

_counter = 0
client: httpx.AsyncClient | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_headers(headers) -> dict:
    out = {}
    for k, v in headers.items():
        out[k] = "<redacted>" if k.lower() in SENSITIVE_HEADERS else v
    return out


def write_record(record: dict) -> None:
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


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


class SSECollector:
    """Ricostruisce il messaggio assistant dagli eventi SSE e ne estrae usage/timing."""

    def __init__(self):
        self.events_count: dict = {}
        self.raw_events: list = []
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
        if SAVE_RAW:
            self.raw_events.append({"event": event_type, "data": payload})

        if event_type == "message_start":
            msg = payload.get("message", {})
            self.message = {k: v for k, v in msg.items() if k != "content"}
            self.usage.update(msg.get("usage", {}))
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
            self.usage.update(payload.get("usage", {}))
            self.stop_reason = payload.get("delta", {}).get("stop_reason")
        elif event_type == "error":
            self.error = payload

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
        result = {
            "type": "sse",
            "message": {**self.message, "content": content},
            "usage": self.usage,
            "stop_reason": self.stop_reason,
            "events_count": self.events_count,
            "content_summary": [
                {
                    "type": b.get("type"),
                    **({"name": b["name"]} if b.get("name") else {}),
                    **({"chars": len(b["text"])} if b.get("text") else {}),
                }
                for b in content
            ],
        }
        if self.error:
            result["error"] = self.error
        if SAVE_RAW:
            result["raw_events"] = self.raw_events
        return result


def fmt_usage(usage: dict) -> str:
    if not usage:
        return "usage n/d"
    parts = [f"input {usage.get('input_tokens', 0)}"]
    if usage.get("cache_read_input_tokens"):
        parts.append(f"cache_read {usage['cache_read_input_tokens']}")
    if usage.get("cache_creation_input_tokens"):
        parts.append(f"cache_write {usage['cache_creation_input_tokens']}")
    parts.append(f"output {usage.get('output_tokens', 0)}")
    return " | ".join(parts)


def print_summary(record: dict) -> None:
    rid = record["id"]
    req, resp = record.get("request", {}), record.get("response", {})
    a = req.get("analysis", {})
    line1 = (
        f"#{rid:03d} {datetime.now():%H:%M:%S} {record['method']} {record['path']} "
        f"{a.get('model', '')} -> {record.get('status')} "
        f"in {record['timing'].get('total_s', 0):.1f}s (ttfb {record['timing'].get('ttfb_s', 0):.1f}s)"
    )
    print(line1)
    if a:
        bits = []
        if "system_chars" in a:
            bits.append(f"system {a['system_chars'] / 1000:.1f}k ch")
        if "tools" in a:
            bits.append(f"tools {a['tools']['count']} ({a['tools']['chars'] / 1000:.0f}k ch)")
        if "messages" in a:
            m = a["messages"]
            bits.append(f"messages {m['count']} ({m['chars'] / 1000:.0f}k ch)")
        if bits:
            print(f"     richiesta: {', '.join(bits)}")
    if resp:
        stop = resp.get("stop_reason")
        tools_used = [c.get("name") for c in resp.get("content_summary", []) if c.get("name")]
        extra = f" | stop {stop}" if stop else ""
        if tools_used:
            extra += f" [{', '.join(tools_used)}]"
        print(f"     risposta:  {fmt_usage(resp.get('usage', {}))}{extra}")
    sys.stdout.flush()


async def proxy(request: Request) -> Response:
    global _counter
    _counter += 1
    rid = _counter
    t_start = time.monotonic()

    raw_body = await request.body()
    try:
        body_json = json.loads(raw_body) if raw_body else None
    except json.JSONDecodeError:
        body_json = None

    record = {
        "id": rid,
        "ts": now_iso(),
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query) if request.url.query else None,
        "timing": {},
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
    url = UPSTREAM + request.url.path + ("?" + request.url.query if request.url.query else "")

    upstream_req = client.build_request(
        request.method, url, headers=upstream_headers, content=raw_body
    )
    try:
        upstream_resp = await client.send(upstream_req, stream=True)
    except httpx.HTTPError as exc:
        record["status"] = None
        record["error"] = f"upstream error: {exc!r}"
        record["timing"]["total_s"] = round(time.monotonic() - t_start, 3)
        write_record(record)
        print_summary(record)
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
                        record["timing"]["ttfb_s"] = round(time.monotonic() - t_start, 3)
                        first = False
                    collector.feed(chunk)
                    yield chunk
            finally:
                await upstream_resp.aclose()
                record["timing"]["total_s"] = round(time.monotonic() - t_start, 3)
                record["response"] = collector.finalize()
                write_record(record)
                print_summary(record)

        return StreamingResponse(
            tee(), status_code=upstream_resp.status_code, headers=resp_headers
        )

    # risposta non in streaming (count_tokens, errori, ecc.)
    data = await upstream_resp.aread()
    await upstream_resp.aclose()
    record["timing"]["ttfb_s"] = round(time.monotonic() - t_start, 3)
    record["timing"]["total_s"] = round(time.monotonic() - t_start, 3)
    try:
        record["response"] = {"type": "json", "body": json.loads(data)}
        usage = record["response"]["body"].get("usage")
        if usage:
            record["response"]["usage"] = usage
    except (json.JSONDecodeError, AttributeError):
        record["response"] = {"type": "raw", "body": data.decode("utf-8", "replace")[:2000]}
    write_record(record)
    print_summary(record)
    return Response(data, status_code=upstream_resp.status_code, headers=resp_headers)


@asynccontextmanager
async def lifespan(app):
    global client
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=15, read=None, write=60, pool=15))
    print(f"agentspy proxy su http://127.0.0.1:{PORT} -> {UPSTREAM}")
    print(f"log: {LOG_FILE}")
    print(f'uso: ANTHROPIC_BASE_URL=http://127.0.0.1:{PORT} claude\n')
    yield
    await client.aclose()


app = Starlette(
    routes=[Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])],
    lifespan=lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
