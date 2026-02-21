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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Wrap with Socket.IO ASGI layer
# ---------------------------------------------------------------------------

# socket_app is the top-level ASGI app passed to uvicorn.
# Socket.IO connections are handled at the root; all other requests are
# forwarded to the inner FastAPI app.
socket_app = create_socket_app(app)

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
