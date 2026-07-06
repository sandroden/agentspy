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


routes = [
    Route("/api/sessions", list_sessions, methods=["GET"]),
    Route("/api/sessions/{session_id}/events", session_events, methods=["GET"]),
    Route("/api/events/{event_id}", get_event, methods=["GET"]),
    Route("/api/sessions/{session_id}/stats", session_stats, methods=["GET"]),
]
