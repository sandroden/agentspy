"""ConnectionManager for the /ws WebSocket: initial hello + live broadcast."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from starlette.websockets import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def serve(self, ws: WebSocket, hello_sessions: Callable[[], Awaitable[list]] | Callable[[], list]) -> None:
        """Accept the connection, send the hello, keep listening until the client closes.

        The channel is server->client: any incoming messages are read only to
        detect the disconnection (no commands from the client in the MVP).
        """
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        try:
            sessions = hello_sessions()
            if asyncio.iscoroutine(sessions):
                sessions = await sessions
            await ws.send_json({"type": "hello", "sessions": sessions})
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            async with self._lock:
                self._connections.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                async with self._lock:
                    self._connections.discard(ws)

    async def broadcast_event(self, event_summary: dict[str, Any]) -> None:
        await self.broadcast({"type": "event", "event": event_summary})

    async def broadcast_session(self, session: dict[str, Any]) -> None:
        await self.broadcast({"type": "session", "session": session})
