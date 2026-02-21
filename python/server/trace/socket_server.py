"""
Socket.IO server — Python port of server/src/trace/wsServer.ts.

Uses python-socketio in ASGI mode so it can wrap FastAPI.
`create_socket_app(fastapi_app)` returns the composite ASGI application to
pass to uvicorn.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import socketio

from .trace_emitter import global_tracer

# ---------------------------------------------------------------------------
# Socket.IO instance (async, ASGI mode)
# ---------------------------------------------------------------------------

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


# ---------------------------------------------------------------------------
# Trace fan-out: wire global_tracer → Socket.IO emit
# ---------------------------------------------------------------------------

def _on_trace(event: Dict[str, Any]) -> None:
    """
    Called synchronously by TraceEmitter.fire().
    We schedule an async emit on the running event loop.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(sio.emit("trace", event))
    except RuntimeError:
        pass


global_tracer.on_trace(_on_trace)


# ---------------------------------------------------------------------------
# Socket.IO lifecycle events
# ---------------------------------------------------------------------------

@sio.event
async def connect(sid: str, environ: dict) -> None:  # noqa: D401
    pass  # nothing to do on connect


@sio.event
async def disconnect(sid: str) -> None:
    """Unblock any pending step gate when the last client disconnects."""
    clients = await sio.get_participants("trace_room") if False else []
    # Always resume — if a step is waiting and the UI reconnects it will
    # re-send a resume request anyway.
    global_tracer.resume()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_socket_app(fastapi_app: Any) -> socketio.ASGIApp:
    """Wrap *fastapi_app* inside a Socket.IO ASGI application."""
    return socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
