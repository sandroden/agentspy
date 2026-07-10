import glob
import json
from pathlib import Path

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from agentspy_server.proxy import (
    ProxyForwarder,
    SSECollector,
    analyze_request_body,
    redact_headers,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SSE_EVENTS = [
    (
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "model": "claude-x",
                "role": "assistant",
                "usage": {"input_tokens": 10, "output_tokens": 0},
            },
        },
    ),
    (
        "content_block_start",
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ),
    (
        "content_block_delta",
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Ciao"}},
    ),
    (
        "content_block_delta",
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " mondo"}},
    ),
    ("content_block_stop", {"type": "content_block_stop", "index": 0}),
    (
        "message_delta",
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}},
    ),
    ("message_stop", {"type": "message_stop"}),
]


def _sse_chunks() -> list[bytes]:
    return [
        f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode()
        for event_type, data in SSE_EVENTS
    ]


async def _upstream_messages(request: Request) -> StreamingResponse:
    async def gen():
        for chunk in _sse_chunks():
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")


upstream_app = Starlette(routes=[Route("/v1/messages", _upstream_messages, methods=["POST"])])


@pytest.mark.asyncio
async def test_proxy_streams_identical_bytes_and_reconstructs_message():
    transport = httpx.ASGITransport(app=upstream_app)
    client = httpx.AsyncClient(transport=transport, base_url="http://upstream")

    captured: dict = {}

    async def on_event(record: dict) -> None:
        captured["record"] = record

    forwarder = ProxyForwarder("http://upstream", client, on_event=on_event)

    async def proxy_view(request: Request):
        return await forwarder.forward(request)

    app = Starlette(routes=[Route("/v1/messages", proxy_view, methods=["POST"])])

    with TestClient(app) as test_client:
        resp = test_client.post(
            "/v1/messages",
            json={"model": "claude-x", "messages": [{"role": "user", "content": "ciao"}]},
            headers={"x-agentspy-tag": "test-tag", "x-api-key": "secret-key"},
        )

    assert resp.status_code == 200
    assert resp.content == b"".join(_sse_chunks())

    await client.aclose()

    record = captured["record"]
    assert record["tag"] == "test-tag"
    assert record["request"]["headers"]["x-api-key"] == "<redacted>"
    response = record["response"]
    assert response["usage"]["input_tokens"] == 10
    assert response["usage"]["output_tokens"] == 5
    assert response["stop_reason"] == "end_turn"
    assert response["message"]["content"][0]["text"] == "Ciao mondo"
    assert record["timing"]["ttfb_s"] is not None
    assert record["timing"]["total_s"] is not None


@pytest.mark.asyncio
async def test_emit_failure_does_not_break_upstream_response():
    """Se lo store (on_event) solleva, Claude Code deve comunque ricevere 200
    con il body upstream intatto: l'emissione è best-effort, fuori dal percorso
    critico."""
    transport = httpx.ASGITransport(app=upstream_app)
    client = httpx.AsyncClient(transport=transport, base_url="http://upstream")

    async def on_event(record: dict) -> None:
        raise RuntimeError("database locked")

    forwarder = ProxyForwarder("http://upstream", client, on_event=on_event)

    async def proxy_view(request: Request):
        return await forwarder.forward(request)

    app = Starlette(routes=[Route("/v1/messages", proxy_view, methods=["POST"])])

    with TestClient(app) as test_client:
        resp = test_client.post(
            "/v1/messages",
            json={"model": "claude-x", "messages": [{"role": "user", "content": "ciao"}]},
        )

    await client.aclose()

    assert resp.status_code == 200
    assert resp.content == b"".join(_sse_chunks())


def _feed_events(collector: SSECollector, events: list[tuple[str, dict]]) -> None:
    for event_type, data in events:
        collector.feed(f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode())


def test_prompt_usage_taken_from_message_start_not_cumulative_delta():
    """Su un turno con extended thinking, message_delta riporta un cache_read
    cumulativo (throughput). L'occupancy della finestra deve restare quella del
    prompt (message_start), non il valore gonfiato del delta. Riproduce il caso
    reale rt19: start cache_read=86747, delta cache_read=181909."""
    collector = SSECollector()
    _feed_events(
        collector,
        [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_thinking",
                        "role": "assistant",
                        "usage": {
                            "input_tokens": 159,
                            "output_tokens": 1,
                            "cache_read_input_tokens": 86747,
                            "cache_creation_input_tokens": 8415,
                        },
                    },
                },
            ),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use"},
                    "usage": {
                        "output_tokens": 7251,
                        "cache_read_input_tokens": 181909,
                        "cache_creation_input_tokens": 11522,
                    },
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ],
    )
    result = collector.finalize()
    usage = result["usage"]
    # prompt (occupancy): dal message_start, non il cumulativo del delta
    assert usage["cache_read_input_tokens"] == 86747
    assert usage["cache_creation_input_tokens"] == 8415
    assert usage["input_tokens"] == 159
    # output: dal message_delta (cresce durante lo streaming)
    assert usage["output_tokens"] == 7251
    assert result["stop_reason"] == "tool_use"


def test_prompt_usage_key_absent_in_start_not_taken_from_delta():
    """Se message_start OMETTE una chiave di prompt (qui
    cache_creation_input_tokens) e message_delta la porta cumulativa, il valore
    gonfiato non deve entrare: le chiavi di prompt sono congelate da
    message_start, non dalla loro semplice presenza nell'accumulo."""
    collector = SSECollector()
    _feed_events(
        collector,
        [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_no_cc",
                        "role": "assistant",
                        "usage": {"input_tokens": 200, "output_tokens": 1},
                    },
                },
            ),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 42, "cache_creation_input_tokens": 99999},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ],
    )
    usage = collector.finalize()["usage"]
    # la chiave assente da message_start non deve essere iniettata dal delta
    assert "cache_creation_input_tokens" not in usage
    assert usage["input_tokens"] == 200
    assert usage["output_tokens"] == 42


def test_midstream_error_marks_stop_reason_error():
    """Uno stream con event error dopo message_start (senza message_delta con
    stop_reason) non deve sembrare riuscito: stop_reason='error' e dettaglio
    conservato in result['error']."""
    collector = SSECollector()
    _feed_events(
        collector,
        [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_err",
                        "role": "assistant",
                        "usage": {"input_tokens": 10, "output_tokens": 0},
                    },
                },
            ),
            (
                "error",
                {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
            ),
        ],
    )
    result = collector.finalize()
    assert result["stop_reason"] == "error"
    assert result["error"]["error"]["type"] == "overloaded_error"


def test_redact_headers_never_leaks_secrets():
    headers = {"x-api-key": "sk-abc", "authorization": "Bearer x", "cookie": "a=b", "user-agent": "curl"}
    redacted = redact_headers(headers)
    assert redacted["x-api-key"] == "<redacted>"
    assert redacted["authorization"] == "<redacted>"
    assert redacted["cookie"] == "<redacted>"
    assert redacted["user-agent"] == "curl"


def test_analyze_request_body_on_real_captured_log():
    """Fixture di realismo: se esiste un log JSONL già catturato dal prototipo,
    verifica che analyze_request_body non esploda su richieste reali."""
    candidates = glob.glob(str(REPO_ROOT / "logs" / "run-*.jsonl"))
    if not candidates:
        pytest.skip("nessun log reale in ../logs, skip fixture di realismo")

    with open(candidates[0]) as f:
        lines = f.readlines()
    assert lines, "log reale vuoto"

    for line in lines:
        record = json.loads(line)
        body = record.get("request", {}).get("body")
        if isinstance(body, dict):
            analysis = analyze_request_body(body)
            assert "model" in analysis
