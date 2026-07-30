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

from agentspy_server.providers.anthropic import (
    AnthropicAdapter,
    SSECollector,
    analyze_request_body,
)
from agentspy_server.proxy import ProxyForwarder, redact_headers

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
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}},
    ),
    (
        "content_block_delta",
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " world"}},
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
            json={"model": "claude-x", "messages": [{"role": "user", "content": "hello"}]},
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
    assert response["message"]["content"][0]["text"] == "Hello world"
    assert record["timing"]["ttfb_s"] is not None
    assert record["timing"]["total_s"] is not None


@pytest.mark.asyncio
async def test_emit_failure_does_not_break_upstream_response():
    """If the store (on_event) raises, Claude Code must still receive 200 with
    the upstream body intact: emission is best-effort, outside the critical
    path."""
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
            json={"model": "claude-x", "messages": [{"role": "user", "content": "hello"}]},
        )

    await client.aclose()

    assert resp.status_code == 200
    assert resp.content == b"".join(_sse_chunks())


def _feed_events(collector: SSECollector, events: list[tuple[str, dict]]) -> None:
    for event_type, data in events:
        collector.feed(f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode())


def test_prompt_usage_taken_from_message_start_not_cumulative_delta():
    """On a turn with extended thinking, message_delta reports a cumulative
    cache_read (throughput). The window occupancy must stay the prompt one
    (message_start), not the inflated delta value. Reproduces the real case
    rt19: start cache_read=86747, delta cache_read=181909."""
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
    # prompt (occupancy): from message_start, not the cumulative delta
    assert usage["cache_read_input_tokens"] == 86747
    assert usage["cache_creation_input_tokens"] == 8415
    assert usage["input_tokens"] == 159
    # output: from message_delta (it grows during streaming)
    assert usage["output_tokens"] == 7251
    assert result["stop_reason"] == "tool_use"


def test_prompt_usage_key_absent_in_start_not_taken_from_delta():
    """If message_start OMITS a prompt key (here cache_creation_input_tokens)
    and message_delta carries it cumulatively, the inflated value must not get
    in: prompt keys are frozen by message_start, not by their mere presence in
    the accumulation."""
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
    # the key missing from message_start must not be injected by the delta
    assert "cache_creation_input_tokens" not in usage
    assert usage["input_tokens"] == 200
    assert usage["output_tokens"] == 42


def test_prompt_usage_from_delta_when_start_reports_none():
    """Anthropic-compatible emulations (OpenRouter) send message_start with
    zeroed usage and the real tokens only in message_delta: if NO prompt token
    came from the start, the delta is the only source and must be accepted
    (observed in E2E with z-ai/glm-4.7-flash via OpenRouter, 2026-07-16)."""
    collector = SSECollector()
    _feed_events(
        collector,
        [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_or",
                        "role": "assistant",
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                },
            ),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"input_tokens": 14870, "output_tokens": 38},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ],
    )
    usage = collector.finalize()["usage"]
    assert usage["input_tokens"] == 14870
    assert usage["output_tokens"] == 38


def test_midstream_error_marks_stop_reason_error():
    """A stream with an error event after message_start (without a
    message_delta carrying stop_reason) must not look successful:
    stop_reason='error' and the detail kept in result['error']."""
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
    """Realism fixture: if a JSONL log already captured by the prototype
    exists, check that analyze_request_body does not blow up on real
    requests."""
    candidates = glob.glob(str(REPO_ROOT / "logs" / "run-*.jsonl"))
    if not candidates:
        pytest.skip("no real log in ../logs, skipping realism fixture")

    with open(candidates[0]) as f:
        lines = f.readlines()
    assert lines, "real log is empty"

    for line in lines:
        record = json.loads(line)
        body = record.get("request", {}).get("body")
        if isinstance(body, dict):
            analysis = analyze_request_body(body)
            assert "model" in analysis


def test_normalize_usage_splits_cache_write_by_ttl():
    """The cache tier (5m vs 1h) reaches the DB columns: the 1h write costs
    twice the input, the 5m one 1.25x, so without the split the cost is
    underestimated. Without cache_creation -> None (unknown tier), not 0."""
    adapter = AnthropicAdapter()
    usage = adapter.normalize_usage(
        {
            "input_tokens": 159,
            "output_tokens": 7251,
            "cache_read_input_tokens": 86747,
            "cache_creation_input_tokens": 8415,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 0,
                "ephemeral_1h_input_tokens": 8415,
            },
        }
    )
    assert usage["cache_write_tokens"] == 8415
    assert usage["cache_write_5m_tokens"] == 0
    assert usage["cache_write_1h_tokens"] == 8415

    plain = adapter.normalize_usage({"input_tokens": 10, "cache_creation_input_tokens": 120})
    assert plain["cache_write_5m_tokens"] is None
    assert plain["cache_write_1h_tokens"] is None
