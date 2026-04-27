"""
EventBus — pluggable async publish/subscribe layer for node execution events.

Architecture
------------
EventBus is a simple Protocol with a single ``publish(event)`` async method.
All execution events (lifecycle trace events and node progress updates) are
routed through an EventBus instance rather than being emitted directly to a
specific transport.

Implementations provided here
------------------------------
  NullEventBus
      No-op default.  Used when no transports are configured (e.g. tests, CLI
      usage without a server).  Zero overhead.

  CompositeEventBus
      Fans out a single publish() call to multiple backend buses concurrently
      via asyncio.gather().  Per-bus exceptions are caught and logged so that
      a failed transport (e.g. a dead RabbitMQ broker) never stops execution.

Transport-specific backends live in python/server/trace/:
  SocketIOEventBus   — wraps the existing global_tracer → sio.emit() pipeline
  RabbitMQEventBus   — aio_pika, topic exchange, persistent delivery

Usage
-----
  # In WorkflowManager._run_executor():
  executor._node_env.event_bus = self.event_bus

  # In a node's compute():
  await executionContext.report_progress(0.5, "Half-way through encoding…")

Extensibility
-------------
Implement the EventBus protocol in any class with:

    async def publish(self, event: dict) -> None: ...
    async def close(self) -> None: ...          # optional but recommended

Then add it to the CompositeEventBus at startup:
    WorkflowManager.instance().configure_bus(
        CompositeEventBus([SocketIOEventBus(), MyCustomBus()])
    )
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EventBus Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class EventBus(Protocol):
    """
    Minimal async pub/sub interface for execution events.

    Any object with an ``async publish(event: dict)`` method satisfies this
    Protocol.  The optional ``close()`` coroutine is called on server shutdown
    to release connections cleanly.
    """

    async def publish(self, event: Dict[str, Any]) -> None:
        """Publish *event* to all interested consumers.

        Implementations must be non-blocking on the happy path and must not
        raise exceptions that would propagate into the Executor's hot loop.
        Use internal try/except and log failures instead.
        """
        ...

    async def close(self) -> None:
        """Release any held resources (connections, threads, etc.)."""
        ...


# ---------------------------------------------------------------------------
# NullEventBus
# ---------------------------------------------------------------------------

class NullEventBus:
    """
    No-op EventBus.  Used as the default when no transports are configured.

    Cost: a single async def with an immediate return — effectively free.
    Satisfies the EventBus Protocol.
    """

    async def publish(self, event: Dict[str, Any]) -> None:  # noqa: D401
        pass

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# CompositeEventBus
# ---------------------------------------------------------------------------

class CompositeEventBus:
    """
    Fans out publish() calls to a list of backend EventBus instances.

    All buses receive the event concurrently (via asyncio.gather with
    return_exceptions=True).  If any individual bus raises, the exception is
    logged at WARNING level but does NOT propagate — execution continues
    regardless of transport failures.

    Parameters
    ----------
    buses : list[EventBus]
        The backend transports to fan out to.  May be empty (equivalent to
        NullEventBus).

    Example
    -------
        bus = CompositeEventBus([SocketIOEventBus(), RabbitMQEventBus()])
        WorkflowManager.instance().configure_bus(bus)
    """

    def __init__(self, buses: List[EventBus]) -> None:
        self._buses = list(buses)

    # ── Public API ────────────────────────────────────────────────────────────

    async def publish(self, event: Dict[str, Any]) -> None:
        if not self._buses:
            return
        results = await asyncio.gather(
            *[bus.publish(event) for bus in self._buses],
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                bus_name = type(self._buses[i]).__name__
                logger.warning(
                    "[EventBus] %s.publish() raised: %s", bus_name, result
                )

    async def close(self) -> None:
        results = await asyncio.gather(
            *[bus.close() for bus in self._buses],
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                bus_name = type(self._buses[i]).__name__
                logger.warning(
                    "[EventBus] %s.close() raised: %s", bus_name, result
                )

    def add_bus(self, bus: EventBus) -> None:
        """Attach an additional backend at runtime."""
        self._buses.append(bus)
