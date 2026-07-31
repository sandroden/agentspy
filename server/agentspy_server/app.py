"""Assembles the Starlette app: /api/*, /ws, /ingest/*, /ui/* (static), catch-all -> proxy.

``create_app()`` builds an isolated instance (its own store/correlator/client):
useful for tests, which pass their own ``db_path``/``upstream``. ``main()`` is
the entry point of the ``agentspy`` script and starts uvicorn with the
configuration from the environment.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from . import api, ingest
from .correlate import Correlator
from .providers import ProviderAdapter, get_provider
from .proxy import ProxyForwarder
from .runtimes import get_runtime
from .store import Store, default_db_path
from .ws import ConnectionManager

logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
DEFAULT_UPSTREAM = "https://api.anthropic.com"
# Correlator rehydration window at startup: sessions whose last activity falls
# within these hours. Override with AGENTSPY_REHYDRATE_HOURS.
DEFAULT_REHYDRATE_HOURS = 48.0
# The server listens on 127.0.0.1 only, but the browser could reach it via a DNS
# name controlled by an attacker (DNS rebinding): TrustedHostMiddleware rejects
# requests with a foreign Host. "testserver" is the default host of Starlette's
# TestClient. Override with AGENTSPY_ALLOWED_HOSTS (CSV list).
DEFAULT_ALLOWED_HOSTS = ["localhost", "127.0.0.1", "::1", "testserver"]


def _allowed_hosts() -> list[str]:
    raw = os.environ.get("AGENTSPY_ALLOWED_HOSTS")
    if not raw:
        return list(DEFAULT_ALLOWED_HOSTS)
    return [h.strip() for h in raw.split(",") if h.strip()]


def _tool_names_from_response(response: dict) -> list[str]:
    message = response.get("message") or {}
    return [
        b.get("name")
        for b in message.get("content", []) or []
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name")
    ]


async def _handle_round_trip(app: Starlette, record: dict) -> None:
    store: Store = app.state.store
    correlator: Correlator = app.state.correlator
    ws_manager: ConnectionManager = app.state.ws_manager
    provider: ProviderAdapter = app.state.provider

    # The proxy emits a record for EVERY forwarded request, but only real model
    # calls are round trips to correlate and persist: the criterion (path, body
    # shape) is known by the provider adapter.
    body = (record.get("request") or {}).get("body")
    if not provider.is_model_call(record.get("path") or "", body if isinstance(body, dict) else None):
        return

    info = correlator.correlate_round_trip(record)
    session_id = info["session_id"]

    # synthetic sessions just identified with a real session (binding via
    # prompt): move the events already saved and notify the clients.
    for merged_id in info.get("merged_from") or []:
        await asyncio.to_thread(store.reassign_session, merged_id, session_id)
        await ws_manager.broadcast({"type": "session_removed", "id": merged_id})

    analysis = (record.get("request") or {}).get("analysis") or {}
    model = analysis.get("model")
    response = record.get("response") or {}
    usage = provider.normalize_usage(response.get("usage") or {})
    stop_reason = response.get("stop_reason")
    timing = record.get("timing") or {}
    ts_start = timing.get("ts_start")
    total_s = timing.get("total_s")
    ts_end = ts_start + total_s if (ts_start is not None and total_s is not None) else ts_start

    # a synthetic attached to a real parent is CLI service traffic: a telling
    # title avoids making it look like a user conversation in the sidebar. The
    # runtime reads from the request WHICH machinery it is (safety check,
    # suggestions, probe...); "service" stays as the fallback for what it does
    # not recognize, and as a weak title it never overwrites a sharper one
    # already found on another round trip of the same session.
    service_title = None
    title_weak = False
    if session_id.startswith("syn-") and info.get("parent_session_id"):
        runtime = app.state.runtime
        service_title = runtime.service_label(body)
        # weak = it must not overwrite a sharper label already found on another
        # round trip: both the fallback and the family-only labels qualify.
        title_weak = service_title is None or service_title in runtime.generic_service_labels
        service_title = service_title or "service"

    await asyncio.to_thread(
        store.upsert_session,
        session_id,
        tag=record.get("tag"),
        title=service_title,
        title_weak=title_weak,
        model=model,
        agent_id=info.get("agent_id"),
        parent_session_id=info.get("parent_session_id"),
        started_at=ts_start,
        ended_at=ts_end,
        live=True,
    )

    event_id = await asyncio.to_thread(
        store.insert_event,
        session_id=session_id,
        kind="round_trip",
        turn_index=info["turn_index"],
        agent_id=info.get("agent_id"),
        ts_start=ts_start,
        ts_end=ts_end,
        ttfb_s=timing.get("ttfb_s"),
        model=model,
        status=record.get("status"),
        stop_reason=stop_reason,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cache_read_tokens=usage.get("cache_read_tokens"),
        cache_write_tokens=usage.get("cache_write_tokens"),
        cache_write_5m_tokens=usage.get("cache_write_5m_tokens"),
        cache_write_1h_tokens=usage.get("cache_write_1h_tokens"),
        tool_names=_tool_names_from_response(response),
        payload=record,
    )

    events = await asyncio.to_thread(store.get_session_events, session_id)
    event_summary = next((e for e in events if e["id"] == event_id), None)
    if event_summary:
        await ws_manager.broadcast_event(event_summary)
    sessions = await asyncio.to_thread(store.get_sessions)
    this_session = next((s for s in sessions if s["id"] == session_id), None)
    if this_session:
        await ws_manager.broadcast_session(this_session)


async def ui_not_built(request: Request) -> Response:
    return JSONResponse(
        {"error": "frontend not built: run the build in frontend/ (npm run build)"},
        status_code=404,
    )


async def root_redirect(request: Request) -> Response:
    return RedirectResponse(url="/ui/")


async def ws_endpoint(websocket: WebSocket) -> None:
    manager: ConnectionManager = websocket.app.state.ws_manager
    store: Store = websocket.app.state.store
    await manager.serve(websocket, lambda: asyncio.to_thread(store.get_sessions))


def create_app(db_path: str | None = None, upstream: str | None = None) -> Starlette:
    upstream = upstream or os.environ.get("AGENTSPY_UPSTREAM", DEFAULT_UPSTREAM)

    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.runtime = get_runtime()
        app.state.store = Store(db_path or default_db_path(), runtime=app.state.runtime)
        app.state.correlator = Correlator(runtime=app.state.runtime)
        # Rehydrate the correlation state from the DB: without it a restart would
        # restart turn_index from 1 and lose the joins by tool_use_id. It is
        # best-effort: on failure it logs and starts empty (never block startup).
        try:
            hours = float(os.environ.get("AGENTSPY_REHYDRATE_HOURS", DEFAULT_REHYDRATE_HOURS))
            snap = app.state.store.rehydration_snapshot(time.time() - hours * 3600)
            app.state.correlator.rehydrate(snap["sessions"], snap["events"])
        except Exception:
            logger.exception("agentspy: correlator rehydration failed, starting empty")
        app.state.ws_manager = ConnectionManager()
        app.state.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15, read=None, write=60, pool=15)
        )
        app.state.provider = get_provider()
        app.state.proxy = ProxyForwarder(
            upstream,
            app.state.client,
            on_event=lambda record: _handle_round_trip(app, record),
            provider=app.state.provider,
        )
        try:
            yield
        finally:
            await app.state.client.aclose()
            app.state.store.close()

    routes = list(api.routes) + list(ingest.routes)
    routes.append(WebSocketRoute("/ws", ws_endpoint))

    if FRONTEND_DIST.is_dir():
        async def ui_spa(request: Request) -> Response:
            """Static with SPA fallback: deep links (/ui/session/<id>) must
            serve index.html and leave the routing to the frontend."""
            rel = request.path_params.get("path") or "index.html"
            candidate = (FRONTEND_DIST / rel).resolve()
            if candidate.is_file() and candidate.is_relative_to(FRONTEND_DIST.resolve()):
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

        routes.append(Route("/ui/{path:path}", ui_spa))
        routes.append(Route("/ui", ui_spa))
    else:
        routes.append(Route("/ui/{path:path}", ui_not_built))
        routes.append(Route("/ui", ui_not_built))

    routes.append(Route("/", root_redirect))

    async def proxy_endpoint(request: Request) -> Response:
        return await request.app.state.proxy.forward(request)

    routes.append(
        Route(
            "/{path:path}",
            proxy_endpoint,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        )
    )

    middleware = [
        Middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts())
    ]
    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)


def main() -> None:
    port = int(os.environ.get("AGENTSPY_PORT", "8082"))
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
