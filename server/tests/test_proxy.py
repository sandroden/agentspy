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

from agentspy_server.proxy import ProxyForwarder, analyze_request_body, redact_headers

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
