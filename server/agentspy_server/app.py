"""Assembla l'app Starlette: /api/*, /ws, /ingest/*, /ui/* (statico), catch-all -> proxy.

``create_app()`` costruisce un'istanza isolata (store/correlator/client propri):
utile per i test, che passano ``db_path``/``upstream`` propri. ``main()`` è
l'entry point dello script ``agentspy`` e lancia uvicorn con la configurazione
da environment.
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
# Finestra di reidratazione del Correlator all'avvio: sessioni con ultima
# attività entro queste ore. Override con AGENTSPY_REHYDRATE_HOURS.
DEFAULT_REHYDRATE_HOURS = 48.0
# Il server ascolta solo su 127.0.0.1, ma il browser potrebbe raggiungerlo via
# un nome DNS controllato da un attaccante (DNS rebinding): TrustedHostMiddleware
# rifiuta le richieste con Host estraneo. "testserver" è l'host di default di
# Starlette TestClient. Override con AGENTSPY_ALLOWED_HOSTS (lista CSV).
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

    # Il proxy emette un record per OGNI richiesta inoltrata, ma solo le vere
    # chiamate al modello sono round trip da correlare e persistere: il
    # criterio (path, forma del body) lo conosce l'adapter del provider.
    body = (record.get("request") or {}).get("body")
    if not provider.is_model_call(record.get("path") or "", body if isinstance(body, dict) else None):
        return

    info = correlator.correlate_round_trip(record)
    session_id = info["session_id"]

    # sessioni sintetiche identificate ora con una sessione reale (binding via
    # prompt): sposta gli eventi già salvati e avvisa i client.
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

    # una sintetica agganciata a una madre reale è traffico di servizio della
    # CLI (titolo di sessione, topic detection...): un titolo parlante evita
    # che in sidebar sembri una conversazione dell'utente
    service_title = (
        "servizio" if session_id.startswith("syn-") and info.get("parent_session_id") else None
    )

    await asyncio.to_thread(
        store.upsert_session,
        session_id,
        tag=record.get("tag"),
        title=service_title,
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
        {"error": "frontend non compilato: esegui la build in frontend/ (npm run build)"},
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
        # Reidrata lo stato di correlazione dal DB: senza, un riavvio farebbe
        # ripartire turn_index da 1 e perderebbe i join per tool_use_id. È
        # best-effort: se fallisce si logga e si parte vuoti (mai bloccare l'avvio).
        try:
            hours = float(os.environ.get("AGENTSPY_REHYDRATE_HOURS", DEFAULT_REHYDRATE_HOURS))
            snap = app.state.store.rehydration_snapshot(time.time() - hours * 3600)
            app.state.correlator.rehydrate(snap["sessions"], snap["events"])
        except Exception:
            logger.exception("agentspy: reidratazione del correlator fallita, parto vuoto")
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
            """Statico con fallback SPA: i deep link (/ui/session/<id>) devono
            servire index.html e lasciare il routing al frontend."""
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
