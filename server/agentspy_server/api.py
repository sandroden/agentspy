"""REST endpoints: GET /api/sessions, /api/sessions/{id}/events, /api/events/{id},
/api/events/{id}/artifact, /api/sessions/{id}/stats.

The store is synchronous (sqlite3): calls are moved onto a thread so uvicorn's
event loop is not blocked during disk I/O.
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


async def artifact_content(request: Request) -> JSONResponse:
    """Content of a context artifact of the event: `?key=<kind>|<path or label>`.

    Separate from `/api/events/{id}` because it is heavy (an entire file, or a
    base64 image) and is only wanted when the user opens the reader.
    """
    store = request.app.state.store
    event_id = int(request.path_params["event_id"])
    key = request.query_params.get("key") or ""
    if not key:
        return JSONResponse({"error": "missing key"}, status_code=400)
    item = await asyncio.to_thread(store.get_artifact_content, event_id, key)
    if item is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(item)


async def session_stats(request: Request) -> JSONResponse:
    store = request.app.state.store
    session_id = request.path_params["session_id"]
    stats = await asyncio.to_thread(store.get_session_stats, session_id)
    return JSONResponse(stats)


async def _delete_and_broadcast(request: Request, ids: list[str]) -> list[str]:
    """Delete the sessions (with descendants) and notify clients over WS with a
    ``session_removed`` for each removed id, so open sidebars update even
    without a refetch."""
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
        return JSONResponse({"error": "missing or invalid 'ids' field"}, status_code=400)
    deleted = await _delete_and_broadcast(request, [str(i) for i in ids])
    return JSONResponse({"deleted": deleted})


routes = [
    Route("/api/sessions", list_sessions, methods=["GET"]),
    Route("/api/sessions/delete", delete_sessions_bulk, methods=["POST"]),
    Route("/api/sessions/{session_id}/events", session_events, methods=["GET"]),
    Route("/api/events/{event_id}", get_event, methods=["GET"]),
    Route("/api/events/{event_id}/artifact", artifact_content, methods=["GET"]),
    Route("/api/sessions/{session_id}/stats", session_stats, methods=["GET"]),
    Route("/api/sessions/{session_id}", delete_session, methods=["DELETE"]),
]
