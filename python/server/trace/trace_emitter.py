"""
TraceEmitter — Python port of server/src/trace/TraceEmitter.ts.

Manages two concerns:
1. Fan-out of trace events to registered listeners (sockets, loggers, etc.)
2. Step-pause gate: callers must `await wait_for_step()` between nodes when
   step mode is active.  The gate is implemented with asyncio.Event objects so
   it integrates naturally with FastAPI / uvicorn's event loop.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional


class TraceEmitter:
    def __init__(self) -> None:
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._step_mode: bool = False
        self._step_events: List[asyncio.Event] = []

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    def on_trace(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback that receives every emitted trace event."""
        self._listeners.append(callback)

    # ------------------------------------------------------------------
    # Emit
    # ------------------------------------------------------------------

    def fire(self, payload: Dict[str, Any]) -> None:
        """Stamp the payload with a millisecond timestamp and broadcast it."""
        if "ts" not in payload:
            payload["ts"] = _now_ms()
        for cb in self._listeners:
            try:
                cb(payload)
            except Exception:
                pass  # never let a listener crash execution

    # ------------------------------------------------------------------
    # Step-pause control
    # ------------------------------------------------------------------

    def enable_step(self) -> None:
        self._step_mode = True

    def disable_step(self) -> None:
        """Disable step mode and release any waiting coroutines immediately."""
        self._step_mode = False
        self.resume()

    async def wait_for_step(self) -> None:
        """
        Pause execution until `resume()` is called (or step mode is off).
        Must be awaited from within the running event loop.
        """
        if not self._step_mode:
            return
        event = asyncio.Event()
        self._step_events.append(event)
        await event.wait()

    def resume(self) -> None:
        """Release all coroutines currently waiting on a step gate."""
        for event in self._step_events:
            event.set()
        self._step_events.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

global_tracer = TraceEmitter()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)
