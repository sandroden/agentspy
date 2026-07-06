"""Endpoint di ingestione: POST /ingest/hook (Claude Code hooks) e POST
/ingest/mcp (wrapper MCP). Correlano l'evento con correlate.Correlator,
salvano su store e notificano via WebSocket.
"""

from __future__ import annotations

import asyncio
import time

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


async def ingest_hook(request: Request) -> JSONResponse:
    store = request.app.state.store
    correlator = request.app.state.correlator
    ws_manager = request.app.state.ws_manager

    body = await request.json()
    payload = body.get("payload") or {}
    tag = body.get("tag")
    ts = body.get("ts") or time.time()

    info = correlator.correlate_hook(payload, tag)
    session_id = info["session_id"]
    hook_name = payload.get("hook_event_name")

    # sessioni sintetiche identificate ora con questa sessione reale: sposta
    # gli eventi già salvati e avvisa i client di dimenticare l'id sintetico.
    for merged_id in info.get("merged_from") or []:
        await asyncio.to_thread(store.reassign_session, merged_id, session_id)
        await ws_manager.broadcast({"type": "session_removed", "id": merged_id})

    # sessione figlia (subagente) scoperta da questo hook: assicura la riga
    # con il legame alla madre; su SubagentStop viene chiusa.
    child = info.get("child_session")
    if child:
        await asyncio.to_thread(
            store.upsert_session,
            child["id"],
            tag=tag,
            title=child.get("agent_type"),
            agent_id=child["agent_id"],
            parent_session_id=child["parent_session_id"],
            started_at=ts,
            ended_at=ts,
            live=not info.get("child_ended"),
        )

    if session_id:
        ending = hook_name in ("Stop", "SubagentStop")
        await asyncio.to_thread(
            store.upsert_session,
            session_id,
            tag=tag,
            agent_id=info.get("agent_id"),
            parent_session_id=info.get("parent_session_id"),
            started_at=ts,
            ended_at=ts,
            live=not ending,
        )

    event_id = await asyncio.to_thread(
        store.insert_event,
        session_id=session_id,
        kind="hook",
        subkind=hook_name,
        turn_index=info.get("turn_index"),
        agent_id=info.get("agent_id"),
        ts_start=ts,
        ts_end=ts,
        payload={"tag": tag, **payload},
    )

    if session_id:
        summary = await asyncio.to_thread(store.get_session_events, session_id)
        event_summary = next((e for e in summary if e["id"] == event_id), None)
        if event_summary:
            await ws_manager.broadcast_event(event_summary)
        sessions = await asyncio.to_thread(store.get_sessions)
        this_session = next((s for s in sessions if s["id"] == session_id), None)
        if this_session:
            await ws_manager.broadcast_session(this_session)

    return JSONResponse({"ok": True, "event_id": event_id, "session_id": session_id})


async def ingest_mcp(request: Request) -> JSONResponse:
    store = request.app.state.store
    ws_manager = request.app.state.ws_manager

    body = await request.json()
    tag = body.get("tag")
    session_id = body.get("session_id")
    server_name = body.get("server_name")
    method = body.get("method")
    ts_request = body.get("ts_request")
    ts_response = body.get("ts_response")
    ts = body.get("ts") or ts_response or ts_request or time.time()

    if session_id:
        await asyncio.to_thread(
            store.upsert_session, session_id, tag=tag, started_at=ts, ended_at=ts, live=True
        )

    subkind = f"{server_name}:{method}" if server_name and method else (method or server_name)
    payload = {k: v for k, v in body.items() if k != "tag"}

    event_id = await asyncio.to_thread(
        store.insert_event,
        session_id=session_id,
        kind="mcp",
        subkind=subkind,
        ts_start=ts_request or ts,
        ts_end=ts_response or ts,
        payload=payload,
    )

    if session_id:
        summary = await asyncio.to_thread(store.get_session_events, session_id)
        event_summary = next((e for e in summary if e["id"] == event_id), None)
        if event_summary:
            await ws_manager.broadcast_event(event_summary)

    return JSONResponse({"ok": True, "event_id": event_id, "session_id": session_id})


routes = [
    Route("/ingest/hook", ingest_hook, methods=["POST"]),
    Route("/ingest/mcp", ingest_mcp, methods=["POST"]),
]
