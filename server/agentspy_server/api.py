"""Endpoint REST: GET /api/sessions, /api/sessions/{id}/events, /api/events/{id},
/api/sessions/{id}/stats.

Lo store è sincrono (sqlite3): le chiamate sono spostate su un thread per non
bloccare l'event loop di uvicorn durante l'I/O su disco.
"""

from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


async def list_sessions(request: Request) -> JSONResponse:
    store = request.app.state.store
    sessions = await asyncio.to_thread(store.get_sessions)
    return JSONResponse(sessions)


async def session_events(request: Request) -> JSONResponse:
    store = request.app.state.store
    session_id = request.path_params["session_id"]
    events = await asyncio.to_thread(store.get_session_events, session_id)
    return JSONResponse(events)


async def get_event(request: Request) -> JSONResponse:
    store = request.app.state.store
    event_id = int(request.path_params["event_id"])
    event = await asyncio.to_thread(store.get_event, event_id)
    if event is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(event)


async def session_stats(request: Request) -> JSONResponse:
    store = request.app.state.store
    session_id = request.path_params["session_id"]
    stats = await asyncio.to_thread(store.get_session_stats, session_id)
    return JSONResponse(stats)


async def _delete_and_broadcast(request: Request, ids: list[str]) -> list[str]:
    """Elimina le sessioni (con discendenti) e notifica i client via WS un
    ``session_removed`` per ciascun id rimosso, così le sidebar aperte si
    aggiornano anche senza refetch."""
    store = request.app.state.store
    ws_manager = request.app.state.ws_manager
    deleted = await asyncio.to_thread(store.delete_sessions, ids)
    for sid in deleted:
        await ws_manager.broadcast({"type": "session_removed", "id": sid})
    return deleted


async def delete_session(request: Request) -> JSONResponse:
    session_id = request.path_params["session_id"]
    deleted = await _delete_and_broadcast(request, [session_id])
    return JSONResponse({"deleted": deleted})


async def delete_sessions_bulk(request: Request) -> JSONResponse:
    body = await request.json()
    ids = body.get("ids") if isinstance(body, dict) else None
    if not isinstance(ids, list):
        return JSONResponse({"error": "campo 'ids' mancante o non valido"}, status_code=400)
    deleted = await _delete_and_broadcast(request, [str(i) for i in ids])
    return JSONResponse({"deleted": deleted})


routes = [
    Route("/api/sessions", list_sessions, methods=["GET"]),
    Route("/api/sessions/delete", delete_sessions_bulk, methods=["POST"]),
    Route("/api/sessions/{session_id}/events", session_events, methods=["GET"]),
    Route("/api/events/{event_id}", get_event, methods=["GET"]),
    Route("/api/sessions/{session_id}/stats", session_stats, methods=["GET"]),
    Route("/api/sessions/{session_id}", delete_session, methods=["DELETE"]),
]
