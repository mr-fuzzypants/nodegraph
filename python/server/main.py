"""
Python FastAPI + Socket.IO server — replaces server/src/main.ts.

Start with:
    cd /Users/robertpringle/development/nodegraph
    python -m nodegraph.python.server.main

Or via uvicorn directly:
    uvicorn nodegraph.python.server.main:socket_app --port 3001 --reload
"""
from __future__ import annotations

import sys
import os
import signal

# Ensure the project root is on sys.path so `nodegraph.*` imports work.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Load .env from the project root (three levels up from this file) so that
# OPENAI_API_KEY and other secrets are available without manual `export`.
try:
    from dotenv import load_dotenv
    _env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", ".env"))
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv not installed; fall back to environment variables

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nodegraph.python.server.routes.graph_routes import router
from nodegraph.python.server.trace.socket_server import create_socket_app

# ---------------------------------------------------------------------------
# Forced-exit signal handler
# ---------------------------------------------------------------------------
# socketio.ASGIApp does NOT forward ASGI lifespan events to the inner FastAPI
# app, so DBOS shutdown hooks never run.  We compensate by:
#   1. Wiring DBOS.launch() / DBOS.destroy() via socket_app on_startup /
#      on_shutdown callbacks instead of FastAPI lifespan (see below).
#   2. Installing a SIGTERM handler that calls os._exit after a brief grace
#      period so the process can always be killed even if threads stall.

def _sigterm_handler(signum, frame):
    """Force-exit within 3 s on SIGTERM/SIGINT if graceful shutdown stalls."""
    import threading, os as _os
    def _force_exit():
        import time
        time.sleep(3)
        _os._exit(0)
    t = threading.Thread(target=_force_exit, daemon=True)
    t.start()

signal.signal(signal.SIGTERM, _sigterm_handler)
# SIGINT is handled by uvicorn; we keep the default so Ctrl+C still
# triggers uvicorn's own graceful shutdown first.

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="NodeGraph API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# ---------------------------------------------------------------------------
# DBOS — durable workflow engine
# ---------------------------------------------------------------------------
# NOTE: We do NOT pass `fastapi=app` to DBOS because socketio.ASGIApp wraps
# the FastAPI instance and does not forward ASGI lifespan events.  That means
# any startup/shutdown handlers DBOS registers on FastAPI would never fire,
# leaving background threads alive and blocking graceful shutdown.
#
# Instead we initialise DBOS config-only here, then call DBOS.launch() and
# DBOS.destroy() explicitly through the socket_app on_startup / on_shutdown
# callbacks below — those ARE called by the Socket.IO ASGI layer.

dbos = None
_dbos_backend: str = "none"

try:
    from dbos import DBOS as _DBOS, DBOSConfig as _DBOSConfig
    # Use DBOS_DATABASE_URL if set; default to a local SQLite file.
    # Examples:
    #   SQLite  (default): sqlite:///nodegraph.sqlite
    #   Postgres          : postgresql://postgres:dbos@localhost:5432/nodegraph
    _db_url = os.environ.get("DBOS_DATABASE_URL", "sqlite:///nodegraph.sqlite")
    # PostgreSQL supports LISTEN/NOTIFY; SQLite requires polling.
    _use_listen_notify = _db_url.startswith(("postgresql://", "postgres://"))
    _dbos_config: _DBOSConfig = {
        "name": "nodegraph",
        "system_database_url": _db_url,
        "use_listen_notify": _use_listen_notify,
    }
    dbos = _DBOS(config=_dbos_config)  # no fastapi= — lifecycle handled below
    _dbos_backend = "PostgreSQL" if _use_listen_notify else "SQLite"
    print(f"[DBOS] Configured ({_dbos_backend}). Will launch on server startup.", flush=True)
except Exception as _dbos_err:
    dbos = None
    print(f"[DBOS] Skipped — durability disabled ({_dbos_err})", flush=True)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Socket.IO ASGI layer with explicit DBOS lifecycle callbacks
# ---------------------------------------------------------------------------
# socket_app is the top-level ASGI app passed to uvicorn.
# on_startup / on_shutdown ARE called by socketio.ASGIApp (unlike FastAPI
# lifespan, which it does not forward).

async def _on_startup() -> None:
    if dbos is not None:
        try:
            _DBOS.launch()
            print(f"[DBOS] Launched ({_dbos_backend}).", flush=True)
        except Exception as _e:
            print(f"[DBOS] launch() failed — {_e}", flush=True)


async def _on_shutdown() -> None:
    if dbos is not None:
        try:
            _DBOS.destroy()
            print("[DBOS] Destroyed cleanly.", flush=True)
        except Exception as _e:
            print(f"[DBOS] destroy() failed — {_e}", flush=True)


socket_app = create_socket_app(app, on_startup=_on_startup, on_shutdown=_on_shutdown)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "nodegraph.python.server.main:socket_app",
        host="0.0.0.0",
        port=3001,
        reload=True,
    )
