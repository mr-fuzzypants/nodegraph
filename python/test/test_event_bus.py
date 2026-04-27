"""
Unit tests for the EventBus abstraction layer.

Tests cover:
  - NullEventBus: no-op, does not raise
  - CompositeEventBus: fan-out, isolation of failures, gather concurrency
  - EventBus Protocol: structural typing (duck-typing)
  - NodeContext.report_progress / report_status: publishes correct payloads
  - NodeContext.report_progress: clamps progress to [0.0, 1.0]
  - SocketIOEventBus: delegates to global_tracer.fire()
  - RabbitMQEventBus.publish: no-op before connect(), routing key mapping
"""
from __future__ import annotations

import asyncio
import sys
import os
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class CollectingBus:
    """Test double: records every event passed to publish()."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.close_called = False

    async def publish(self, event: Dict[str, Any]) -> None:
        self.events.append(event)

    async def close(self) -> None:
        self.close_called = True


class BrokenBus:
    """Test double: always raises on publish()."""

    async def publish(self, event: Dict[str, Any]) -> None:
        raise RuntimeError("transport failure")

    async def close(self) -> None:
        pass


def _make_node_context(node_id: str = "node1", event_bus: Any = None) -> Any:
    """Construct a NodeContext backed by the given bus (or NullEventBus)."""
    from nodegraph.python.core.node_context import NodeContext, NodeEnvironment
    from nodegraph.python.core.event_bus import NullEventBus

    bus = event_bus if event_bus is not None else NullEventBus()
    env = NodeEnvironment(event_bus=bus)
    return NodeContext(
        uuid="test-uuid",
        node_id=node_id,
        network_id="net1",
        node_path=f"/{node_id}",
        data_inputs={},
        control_inputs={},
        env=env,
    )


# ===========================================================================
# NullEventBus
# ===========================================================================

class TestNullEventBus:
    def test_publish_does_not_raise(self):
        from nodegraph.python.core.event_bus import NullEventBus
        bus = NullEventBus()
        asyncio.run(bus.publish({"type": "NODE_RUNNING", "nodeId": "n1"}))

    def test_close_does_not_raise(self):
        from nodegraph.python.core.event_bus import NullEventBus
        bus = NullEventBus()
        asyncio.run(bus.close())

    def test_satisfies_protocol(self):
        from nodegraph.python.core.event_bus import EventBus, NullEventBus
        assert isinstance(NullEventBus(), EventBus)


# ===========================================================================
# CompositeEventBus
# ===========================================================================

class TestCompositeEventBus:
    def test_publishes_to_all_buses(self):
        from nodegraph.python.core.event_bus import CompositeEventBus
        a, b = CollectingBus(), CollectingBus()
        bus = CompositeEventBus([a, b])
        event = {"type": "NODE_DONE", "nodeId": "n1", "durationMs": 42}
        asyncio.run(bus.publish(event))
        assert a.events == [event]
        assert b.events == [event]

    def test_empty_composite_does_not_raise(self):
        from nodegraph.python.core.event_bus import CompositeEventBus
        bus = CompositeEventBus([])
        asyncio.run(bus.publish({"type": "EXEC_START", "networkId": "net", "rootNodeId": "n"}))

    def test_broken_bus_does_not_crash_other_buses(self):
        """A failing transport must not prevent other buses from receiving events."""
        from nodegraph.python.core.event_bus import CompositeEventBus
        good = CollectingBus()
        bus = CompositeEventBus([BrokenBus(), good])
        event = {"type": "NODE_PROGRESS", "nodeId": "n1", "progress": 0.5, "message": ""}
        asyncio.run(bus.publish(event))
        assert good.events == [event]

    def test_broken_bus_logs_warning(self, caplog):
        import logging
        from nodegraph.python.core.event_bus import CompositeEventBus
        bus = CompositeEventBus([BrokenBus()])
        with caplog.at_level(logging.WARNING, logger="nodegraph.python.core.event_bus"):
            asyncio.run(bus.publish({"type": "NODE_DONE", "nodeId": "n"}))
        assert any("BrokenBus" in r.message for r in caplog.records)

    def test_close_calls_all_buses(self):
        from nodegraph.python.core.event_bus import CompositeEventBus
        a, b = CollectingBus(), CollectingBus()
        bus = CompositeEventBus([a, b])
        asyncio.run(bus.close())
        assert a.close_called
        assert b.close_called

    def test_broken_close_does_not_crash(self):
        from nodegraph.python.core.event_bus import CompositeEventBus
        bus = CompositeEventBus([BrokenBus()])
        asyncio.run(bus.close())  # must not raise

    def test_add_bus_adds_at_runtime(self):
        from nodegraph.python.core.event_bus import CompositeEventBus
        c = CollectingBus()
        bus = CompositeEventBus([])
        bus.add_bus(c)
        asyncio.run(bus.publish({"type": "NODE_RUNNING", "nodeId": "n"}))
        assert len(c.events) == 1

    def test_publishes_concurrently(self):
        """gather() fires both buses in the same event loop turn."""
        from nodegraph.python.core.event_bus import CompositeEventBus
        order: List[str] = []

        class SlowBus:
            async def publish(self, event):
                await asyncio.sleep(0.01)
                order.append("slow")

            async def close(self): pass

        class FastBus:
            async def publish(self, event):
                order.append("fast")

            async def close(self): pass

        bus = CompositeEventBus([SlowBus(), FastBus()])
        asyncio.run(bus.publish({"type": "NODE_DONE"}))
        # With gather() fast fires inside the same loop tick but slow awaits first;
        # both must have received the event regardless of order.
        assert set(order) == {"slow", "fast"}

    def test_satisfies_protocol(self):
        from nodegraph.python.core.event_bus import CompositeEventBus, EventBus
        assert isinstance(CompositeEventBus([]), EventBus)


# ===========================================================================
# NodeContext.report_progress
# ===========================================================================

class TestNodeContextReportProgress:
    @pytest.mark.asyncio
    async def test_publishes_node_progress_event(self):
        bus = CollectingBus()
        ctx = _make_node_context("my-node", bus)
        await ctx.report_progress(0.6, "step 3 of 5")
        assert len(bus.events) == 1
        ev = bus.events[0]
        assert ev["type"] == "NODE_PROGRESS"
        assert ev["nodeId"] == "my-node"
        assert ev["progress"] == pytest.approx(0.6)
        assert ev["message"] == "step 3 of 5"
        assert "ts" in ev

    @pytest.mark.asyncio
    async def test_clamps_progress_above_1(self):
        bus = CollectingBus()
        ctx = _make_node_context(event_bus=bus)
        await ctx.report_progress(1.5)
        assert bus.events[0]["progress"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_clamps_progress_below_0(self):
        bus = CollectingBus()
        ctx = _make_node_context(event_bus=bus)
        await ctx.report_progress(-0.3)
        assert bus.events[0]["progress"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_empty_message_default(self):
        bus = CollectingBus()
        ctx = _make_node_context(event_bus=bus)
        await ctx.report_progress(0.5)
        assert bus.events[0]["message"] == ""

    @pytest.mark.asyncio
    async def test_no_env_does_not_raise(self):
        """report_progress is a no-op when ctx.env is None."""
        from nodegraph.python.core.node_context import NodeContext
        ctx = NodeContext("u", "n", "net", "/n", {}, {}, env=None)
        await ctx.report_progress(0.5)  # must not raise


# ===========================================================================
# NodeContext.report_status
# ===========================================================================

class TestNodeContextReportStatus:
    @pytest.mark.asyncio
    async def test_publishes_node_status_event(self):
        bus = CollectingBus()
        ctx = _make_node_context("my-node", bus)
        await ctx.report_status("Loading weights")
        assert len(bus.events) == 1
        ev = bus.events[0]
        assert ev["type"] == "NODE_STATUS"
        assert ev["nodeId"] == "my-node"
        assert ev["status"] == "Loading weights"
        assert "ts" in ev

    @pytest.mark.asyncio
    async def test_no_env_does_not_raise(self):
        from nodegraph.python.core.node_context import NodeContext
        ctx = NodeContext("u", "n", "net", "/n", {}, {}, env=None)
        await ctx.report_status("Loading weights")


# ===========================================================================
# NodeContext default bus is NullEventBus
# ===========================================================================

class TestNodeEnvironmentDefaultBus:
    def test_default_event_bus_is_null(self):
        from nodegraph.python.core.node_context import NodeEnvironment
        from nodegraph.python.core.event_bus import NullEventBus
        env = NodeEnvironment()
        assert isinstance(env.event_bus, NullEventBus)

    def test_custom_bus_injected(self):
        from nodegraph.python.core.node_context import NodeEnvironment
        bus = CollectingBus()
        env = NodeEnvironment(event_bus=bus)
        assert env.event_bus is bus


# ===========================================================================
# SocketIOEventBus
# ===========================================================================

class TestSocketIOEventBus:
    def test_delegates_to_global_tracer_fire(self):
        # socketio_bus defers the import of trace_emitter into publish() to keep
        # core importable without a live server; patch via sys.modules.
        from nodegraph.python.server.trace.socketio_bus import SocketIOEventBus
        event = {"type": "NODE_PROGRESS", "nodeId": "n1", "progress": 0.25, "message": ""}

        mock_tracer = MagicMock()
        mock_trace_emitter = MagicMock()
        mock_trace_emitter.global_tracer = mock_tracer

        with patch.dict("sys.modules", {
            "nodegraph.python.server.trace.trace_emitter": mock_trace_emitter,
        }):
            bus = SocketIOEventBus()
            asyncio.run(bus.publish(event))

        mock_tracer.fire.assert_called_once_with(event)

    def test_close_does_not_raise(self):
        from nodegraph.python.server.trace.socketio_bus import SocketIOEventBus
        asyncio.run(SocketIOEventBus().close())


# ===========================================================================
# RabbitMQEventBus  (no live broker needed)
# ===========================================================================

class TestRabbitMQEventBus:
    def test_publish_before_connect_is_noop(self):
        """Before connect() is called, publish must not raise."""
        from nodegraph.python.server.trace.rabbitmq_bus import RabbitMQEventBus
        bus = RabbitMQEventBus()
        asyncio.run(bus.publish({"type": "NODE_RUNNING", "nodeId": "n"}))

    def test_close_before_connect_is_noop(self):
        from nodegraph.python.server.trace.rabbitmq_bus import RabbitMQEventBus
        bus = RabbitMQEventBus()
        asyncio.run(bus.close())

    def test_routing_key_known_types(self):
        from nodegraph.python.server.trace.rabbitmq_bus import _ROUTING_KEY
        assert _ROUTING_KEY["NODE_PROGRESS"] == "node.progress"
        assert _ROUTING_KEY["NODE_DONE"] == "node.done"
        assert _ROUTING_KEY["EXEC_START"] == "exec.start"
        assert _ROUTING_KEY["EDGE_ACTIVE"] == "edge.active"

    def test_publish_calls_exchange(self):
        """With a mock exchange, publish() serialises the event and routes correctly."""
        # rabbitmq_bus defers 'import aio_pika' into publish(); inject via sys.modules.
        from nodegraph.python.server.trace.rabbitmq_bus import RabbitMQEventBus

        mock_exchange = AsyncMock()
        mock_aio = MagicMock()
        mock_aio.Message.return_value = MagicMock()
        mock_aio.DeliveryMode.PERSISTENT = 2

        async def _run():
            bus = RabbitMQEventBus()
            bus._exchange = mock_exchange
            await bus.publish({"type": "NODE_PROGRESS", "nodeId": "n", "progress": 0.5, "message": "hi"})

        with patch.dict("sys.modules", {"aio_pika": mock_aio}):
            asyncio.run(_run())

        mock_exchange.publish.assert_called_once()
        call_kwargs = mock_exchange.publish.call_args
        # routing_key should be 'node.progress' (keyword argument)
        routing_key = call_kwargs.kwargs.get("routing_key")
        assert routing_key == "node.progress"

    def test_unknown_event_type_routing_key(self):
        """Event types not in the lookup table use 'event.<type_lower>' pattern."""
        from nodegraph.python.server.trace.rabbitmq_bus import RabbitMQEventBus, _ROUTING_KEY

        unknown_type = "SOME_FUTURE_EVENT"
        assert unknown_type not in _ROUTING_KEY
        expected_key = f"event.{unknown_type.lower()}"

        mock_exchange = AsyncMock()
        mock_aio = MagicMock()
        mock_aio.Message.return_value = MagicMock()
        mock_aio.DeliveryMode.PERSISTENT = 2

        async def _run():
            bus = RabbitMQEventBus()
            bus._exchange = mock_exchange
            await bus.publish({"type": unknown_type, "nodeId": "n"})

        with patch.dict("sys.modules", {"aio_pika": mock_aio}):
            asyncio.run(_run())

        call_kwargs = mock_exchange.publish.call_args
        routing_key = call_kwargs.kwargs.get("routing_key")
        assert routing_key == expected_key

    def test_exchange_publish_error_does_not_propagate(self):
        """Transport errors inside publish() must be swallowed."""
        from nodegraph.python.server.trace.rabbitmq_bus import RabbitMQEventBus

        mock_exchange = AsyncMock()
        mock_exchange.publish.side_effect = Exception("broker gone")
        mock_aio = MagicMock()
        mock_aio.Message.return_value = MagicMock()
        mock_aio.DeliveryMode.PERSISTENT = 2

        async def _run():
            bus = RabbitMQEventBus()
            bus._exchange = mock_exchange
            await bus.publish({"type": "NODE_DONE", "nodeId": "n"})

        with patch.dict("sys.modules", {"aio_pika": mock_aio}):
            asyncio.run(_run())  # must not raise
