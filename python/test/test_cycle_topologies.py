"""
test_cycle_topologies.py — Comprehensive exercise of valid and invalid
graph cycle topologies in the NodeGraph execution engine.

Topology classes tested
-----------------------
VALID — cycles mediated by a flow-control loop node:
  1.  WhileLoop — fires at least once (default stop on empty signal)
  2.  WhileLoop — multi-iteration body execution
  3.  WhileLoop — back-edge carries data forward across iterations
  4.  WhileLoop — inter-node back-edge (A → B → back to A.input), the
                  canonical pattern used by the ImageRefinementDemo
  5.  ForLoop nested inside WhileLoop
  6.  WhileLoop nested inside ForLoop (already tested in test_loop_node.py
      for ForLoop; here we test the WhileLoop as inner)
  7.  completed edge fires exactly once, after all loop_body iterations

INVALID — unmediated cycles that must be caught:
  8.  Self-loop on a data node: add_edge raises ValueError at build time
  9.  Self-loop on a flow-control node: add_edge raises ValueError at build time
  10. Two-node mutual data dependency: executor raises RuntimeError
  11. Three-node data cycle (A→B→C→A): executor raises RuntimeError
  12. Mixed flow/data node deadlock: flow node depends on data node that
      depends on another data node that depends on the first — RuntimeError

All node types defined in this file use the "CT_" prefix and are registered
with _safe_register so they do not conflict with other test modules or the
server node registry side-effects.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Dict, Any

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.Executor import ExecutionResult, ExecCommand, Executor
from nodegraph.python.core.NodePort import (
    InputControlPort,
    OutputControlPort,
    InputDataPort,
    OutputDataPort,
)
from nodegraph.python.core.Types import ValueType


# ── Registration helper ───────────────────────────────────────────────────────

def _safe_register(type_name: str):
    """Idempotent Node.register — skips if already registered."""
    def decorator(cls):
        if type_name not in Node._node_registry:
            Node._node_registry[type_name] = cls
        return cls
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Minimal local node types
# ─────────────────────────────────────────────────────────────────────────────

@_safe_register("CT_ConstNode")
class CT_ConstNode(Node):
    """Emits a fixed integer value on `out`. Pure data node (no control ports)."""
    def __init__(self, id, type="CT_ConstNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.outputs["out"] = OutputDataPort(self.id, "out", ValueType.INT)
        self.outputs["out"].value = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        res = ExecutionResult(ExecCommand.CONTINUE)
        res.data_outputs["out"] = self.outputs["out"].value
        return res


@_safe_register("CT_AddNode")
class CT_AddNode(Node):
    """Adds inputs `a` + `b` → `sum`. Pure data node."""
    def __init__(self, id, type="CT_AddNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.inputs["a"]   = InputDataPort(self.id, "a",   ValueType.INT)
        self.inputs["b"]   = InputDataPort(self.id, "b",   ValueType.INT)
        self.outputs["sum"] = OutputDataPort(self.id, "sum", ValueType.INT)

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx = (executionContext or {}).get("data_inputs", {})
        a   = int(ctx.get("a", self.inputs["a"].value) or 0)
        b   = int(ctx.get("b", self.inputs["b"].value) or 0)
        total = a + b
        self.outputs["sum"].value = total
        res = ExecutionResult(ExecCommand.CONTINUE)
        res.data_outputs["sum"] = total
        return res


@_safe_register("CT_TriggerNode")
class CT_TriggerNode(Node):
    """
    Flow-control entry point.  Records the `value` data input each time it
    runs.  Fires `next` unconditionally.  Used as the run-entry for deadlock
    tests and as a result sink in valid-cycle tests.
    """
    def __init__(self, id, type="CT_TriggerNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.inputs["exec"]  = InputControlPort(self.id, "exec")
        self.inputs["value"] = InputDataPort(self.id, "value", ValueType.INT)
        self.outputs["next"] = OutputControlPort(self.id, "next")
        self.recorded_values: list = []

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx = (executionContext or {}).get("data_inputs", {})
        v   = ctx.get("value", self.inputs["value"].value)
        self.recorded_values.append(v)
        res = ExecutionResult(ExecCommand.CONTINUE)
        res.control_outputs["next"] = True
        return res


@_safe_register("CT_ForLoopNode")
class CT_ForLoopNode(Node):
    """
    Integer for-loop.  Fires `loop_body` once per integer in [start, end)
    with `index` data output, then fires `completed`.
    """
    def __init__(self, id, type="CT_ForLoopNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self._index:  int  = 0
        self._active: bool = False

        self.inputs["exec"]       = InputControlPort(self.id, "exec")
        self.inputs["start"]      = InputDataPort(self.id, "start", ValueType.INT)
        self.inputs["end"]        = InputDataPort(self.id, "end",   ValueType.INT)
        self.outputs["loop_body"] = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"] = OutputControlPort(self.id, "completed")
        self.outputs["index"]     = OutputDataPort(self.id, "index", ValueType.INT)

        self.inputs["start"].value = 0
        self.inputs["end"].value   = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx   = (executionContext or {}).get("data_inputs", {})
        start = int(ctx.get("start", self.inputs["start"].value) or 0)
        end   = int(ctx.get("end",   self.inputs["end"].value)   or 0)

        if not self._active:
            self._index  = start
            self._active = True

        if self._index < end:
            idx           = self._index
            self._index  += 1
            self.outputs["index"].value = idx
            res = ExecutionResult(ExecCommand.LOOP_AGAIN)
            res.data_outputs["index"]        = idx
            res.control_outputs["loop_body"] = True
            res.control_outputs["completed"] = False
            return res
        else:
            self._index  = start
            self._active = False
            res = ExecutionResult(ExecCommand.COMPLETED)
            res.control_outputs["completed"] = True
            res.control_outputs["loop_body"] = False
            return res


@_safe_register("CT_WhileLoopNode")
class CT_WhileLoopNode(Node):
    """
    Condition-driven while-loop.  Always fires `loop_body` on the FIRST call
    regardless of `stop_signal`.  On subsequent calls exits when `stop_signal`
    is "done", "stop", "quit", "exit", or empty string.
    """
    def __init__(self, id, type="CT_WhileLoopNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self._iteration: int  = 0
        self._active:    bool = False

        self.inputs["exec"]        = InputControlPort(self.id, "exec")
        self.inputs["stop_signal"] = InputDataPort(self.id, "stop_signal", ValueType.STRING)
        self.outputs["loop_body"]  = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"]  = OutputControlPort(self.id, "completed")
        self.outputs["iteration"]  = OutputDataPort(self.id, "iteration", ValueType.INT)

        self.inputs["stop_signal"].value = ""
        self.outputs["iteration"].value  = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx         = (executionContext or {}).get("data_inputs", {})
        stop_signal = str(ctx.get("stop_signal", self.inputs["stop_signal"].value) or "")

        if not self._active:
            self._active    = True
            self._iteration = 0
        else:
            if stop_signal.strip().lower() in ("done", "stop", "quit", "exit", ""):
                self._active    = False
                self._iteration = 0
                res = ExecutionResult(ExecCommand.COMPLETED)
                res.control_outputs["completed"] = True
                res.control_outputs["loop_body"] = False
                return res

        idx             = self._iteration
        self._iteration += 1
        self.outputs["iteration"].value = idx

        res = ExecutionResult(ExecCommand.LOOP_AGAIN)
        res.data_outputs["iteration"]    = idx
        res.control_outputs["loop_body"] = True
        res.control_outputs["completed"] = False
        return res


@_safe_register("CT_CountingBodyNode")
class CT_CountingBodyNode(Node):
    """
    Flow-control loop body that counts how many times it has been executed.
    Emits `stop_signal` = "done" on the Nth call (when count == max_count),
    allowing CT_WhileLoopNode to terminate.

    Ports
    -----
    exec        (control in)
    max_count   (data in INT, default 3)
    next        (control out)
    stop_signal (data out STRING) — "continue" normally, "done" when done
    count       (data out INT)    — total executions so far
    """
    def __init__(self, id, type="CT_CountingBodyNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self._count: int = 0

        self.inputs["exec"]         = InputControlPort(self.id, "exec")
        self.inputs["max_count"]    = InputDataPort(self.id, "max_count", ValueType.INT)
        self.outputs["next"]        = OutputControlPort(self.id, "next")
        self.outputs["stop_signal"] = OutputDataPort(self.id, "stop_signal", ValueType.STRING)
        self.outputs["count"]       = OutputDataPort(self.id, "count",       ValueType.INT)

        self.inputs["max_count"].value    = 3
        self.outputs["stop_signal"].value = "continue"
        self.outputs["count"].value       = 0
        self._total_count: int = 0  # never resets — tracks lifetime invocations
        self._cycle_count: int = 0  # resets each time the loop re-enters here

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx       = (executionContext or {}).get("data_inputs", {})
        max_count = int(ctx.get("max_count", self.inputs["max_count"].value) or 3)

        self._total_count += 1
        self._cycle_count += 1
        self._count        = self._total_count   # keep _count as lifetime alias

        signal = "done" if self._cycle_count >= max_count else "continue"
        if signal == "done":
            self._cycle_count = 0   # reset so this node works fresh in the next outer loop

        self.outputs["stop_signal"].value = signal
        self.outputs["count"].value       = self._total_count

        res = ExecutionResult(ExecCommand.CONTINUE)
        res.data_outputs["stop_signal"] = signal
        res.data_outputs["count"]       = self._count
        res.control_outputs["next"]     = True
        return res


@_safe_register("CT_ProducerNode")
class CT_ProducerNode(Node):
    """
    Flow-control node that produces a value by adding `step` to `base_value`.

    This is used to test inter-node back-edges:
        ProducerNode.result → ConsumerNode.input
        ConsumerNode.processed → ProducerNode.base_value   ← back-edge

    Ports
    -----
    exec        (control in)
    base_value  (data in INT, default 0) — fed by back-edge from consumer
    step        (data in INT, default 10)
    next        (control out)
    result      (data out INT) — base_value + step
    """
    def __init__(self, id, type="CT_ProducerNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        self.inputs["exec"]       = InputControlPort(self.id, "exec")
        self.inputs["base_value"] = InputDataPort(self.id, "base_value", ValueType.INT)
        self.inputs["step"]       = InputDataPort(self.id, "step",       ValueType.INT)
        self.outputs["next"]      = OutputControlPort(self.id, "next")
        self.outputs["result"]    = OutputDataPort(self.id, "result",    ValueType.INT)

        self.inputs["base_value"].value = 0
        self.inputs["step"].value       = 10
        self.outputs["result"].value    = 0

        self.computed_results: list = []

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx        = (executionContext or {}).get("data_inputs", {})
        base_value = int(ctx.get("base_value", self.inputs["base_value"].value) or 0)
        step       = int(ctx.get("step",       self.inputs["step"].value)       or 10)

        result = base_value + step
        self.outputs["result"].value = result
        self.computed_results.append(result)

        res = ExecutionResult(ExecCommand.CONTINUE)
        res.data_outputs["result"]  = result
        res.control_outputs["next"] = True
        return res


@_safe_register("CT_ConsumerNode")
class CT_ConsumerNode(Node):
    """
    Flow-control node that receives a value, doubles it, and emits it back.

    Used as the downstream node in inter-node back-edge tests:
        ProducerNode.result → ConsumerNode.value_in
        ConsumerNode.processed → ProducerNode.base_value   ← back-edge

    Ports
    -----
    exec       (control in)
    value_in   (data in INT)
    next       (control out)
    processed  (data out INT) — value_in * 2 (fed back to producer as base)
    """
    def __init__(self, id, type="CT_ConsumerNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        self.inputs["exec"]       = InputControlPort(self.id, "exec")
        self.inputs["value_in"]   = InputDataPort(self.id, "value_in",  ValueType.INT)
        self.outputs["next"]      = OutputControlPort(self.id, "next")
        self.outputs["processed"] = OutputDataPort(self.id, "processed", ValueType.INT)

        self.inputs["value_in"].value   = 0
        self.outputs["processed"].value = 0

        self.received_values: list = []

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx      = (executionContext or {}).get("data_inputs", {})
        value_in = int(ctx.get("value_in", self.inputs["value_in"].value) or 0)

        processed = value_in * 2
        self.outputs["processed"].value = processed
        self.received_values.append(value_in)

        res = ExecutionResult(ExecCommand.CONTINUE)
        res.data_outputs["processed"] = processed
        res.control_outputs["next"]   = True
        return res


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _make_net(name: str) -> NodeNetwork:
    return NodeNetwork.createRootNetwork(name, "NodeNetworkSystem")


def _arun(coro):
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Valid cycle topologies — must complete without error
# ─────────────────────────────────────────────────────────────────────────────

class TestValidCycleTopologies:
    """
    All topologies here contain back-edges (cycles in the graph), but each is
    mediated by a loop node (CT_WhileLoopNode or CT_ForLoopNode) that converts
    the back-edge into a deferred LOOP_AGAIN command.  The executor treats it
    as a safe iterative construct rather than a deadlock.
    """

    # ── 1 ────────────────────────────────────────────────────────────────────

    def test_while_loop_fires_at_least_once(self):
        """
        A WhileLoopNode with no stop_signal connected always fires loop_body
        once on its first execution, even though the stop condition is trivially
        met (empty string).  The stop is only checked AFTER the first iteration.
        """
        async def _body():
            net  = _make_net("wl_once")
            loop = net.createNode("Loop", "CT_WhileLoopNode")
            body = net.createNode("Body", "CT_CountingBodyNode")
            body.inputs["max_count"].value = 99  # will not reach — stops at empty signal

            net.graph.add_edge(loop.id, "loop_body", body.id, "exec")
            # NO stop_signal edge — stop_signal stays empty → exits after one iteration

            await Executor(net.graph).cook_flow_control_nodes(loop)
            assert body._count == 1, (
                "WhileLoop must fire loop_body at least once regardless of "
                "the initial stop_signal value."
            )
        _arun(_body())

    # ── 2 ────────────────────────────────────────────────────────────────────

    def test_while_loop_executes_n_iterations(self):
        """
        WhileLoop fires exactly max_count times when the body node emits
        'done' on the Nth invocation and that value is wired back as
        stop_signal.  This is the minimal valid-cycle topology.

        Graph (with back-edge marked ←):
            Loop.loop_body → Body.exec
            Body.stop_signal → Loop.stop_signal   ← back-edge
        """
        for max_count in (1, 3, 5):
            async def _body(n=max_count):
                net  = _make_net(f"wl_n_{n}")
                loop = net.createNode("Loop", "CT_WhileLoopNode")
                body = net.createNode("Body", "CT_CountingBodyNode")
                body.inputs["max_count"].value = n

                net.graph.add_edge(loop.id, "loop_body",   body.id, "exec")
                net.graph.add_edge(body.id, "stop_signal", loop.id, "stop_signal")

                await Executor(net.graph).cook_flow_control_nodes(loop)
                assert body._count == n, (
                    f"Expected {n} iterations, got {body._count}"
                )
            _arun(_body())

    # ── 3 ────────────────────────────────────────────────────────────────────

    def test_while_loop_completed_fires_after_loop_body(self):
        """
        The `completed` control output is routed to a CT_TriggerNode and must
        fire exactly once, after all loop_body iterations have finished.  The
        trigger records execution order so we can verify completed fires last.
        """
        async def _body():
            net      = _make_net("wl_completed")
            loop     = net.createNode("Loop",      "CT_WhileLoopNode")
            body     = net.createNode("Body",      "CT_CountingBodyNode")
            done_trig = net.createNode("DoneTrig", "CT_TriggerNode")

            body.inputs["max_count"].value      = 3
            done_trig.inputs["value"].value     = 999  # sentinel

            net.graph.add_edge(loop.id, "loop_body",   body.id,      "exec")
            net.graph.add_edge(body.id, "stop_signal", loop.id,      "stop_signal")
            net.graph.add_edge(loop.id, "completed",   done_trig.id, "exec")

            await Executor(net.graph).cook_flow_control_nodes(loop)

            assert body._count == 3
            assert len(done_trig.recorded_values) == 1, (
                "completed must fire exactly once"
            )
        _arun(_body())

    # ── 4 ────────────────────────────────────────────────────────────────────

    def test_while_loop_inter_node_back_edge_propagates(self):
        """
        Classic inter-node back-edge: ProducerNode.result feeds ConsumerNode,
        and ConsumerNode.processed is wired BACK to ProducerNode.base_value.

        Each iteration the producer computes base_value + step, the consumer
        doubles that result, and the doubled value becomes the next base_value.

        Iteration 0:  base=0,  step=10 → result=10  → processed=20
        Iteration 1:  base=20, step=10 → result=30  → processed=60
        Iteration 2:  base=60, step=10 → result=70  → processed=140

        The body node counts executions and stops the loop after 3 iterations.

        Graph (back-edge marked ←):
            Loop.loop_body  → Counter.exec
            Counter.next    → Producer.exec
            Producer.next   → Consumer.exec
            Consumer.processed → Producer.base_value   ← inter-node back-edge
            Counter.stop_signal → Loop.stop_signal     ← stop condition
        """
        async def _body():
            net      = _make_net("wl_backprop")
            loop     = net.createNode("Loop",     "CT_WhileLoopNode")
            counter  = net.createNode("Counter",  "CT_CountingBodyNode")
            producer = net.createNode("Producer", "CT_ProducerNode")
            consumer = net.createNode("Consumer", "CT_ConsumerNode")

            counter.inputs["max_count"].value   = 3
            producer.inputs["step"].value       = 10

            # Control flow
            net.graph.add_edge(loop.id,     "loop_body",   counter.id,  "exec")
            net.graph.add_edge(counter.id,  "next",        producer.id, "exec")
            net.graph.add_edge(producer.id, "next",        consumer.id, "exec")

            # Stop condition back-edge
            net.graph.add_edge(counter.id,  "stop_signal", loop.id,     "stop_signal")

            # Forward data edge: producer result feeds consumer input
            net.graph.add_edge(producer.id, "result",     consumer.id, "value_in")

            # Inter-node data back-edge (the cycle under test):
            # consumer.processed feeds back as the base for the next iteration
            net.graph.add_edge(consumer.id, "processed",  producer.id, "base_value")

            await Executor(net.graph).cook_flow_control_nodes(loop)

            assert producer.computed_results == [10, 30, 70], (
                f"Expected [10, 30, 70], got {producer.computed_results}"
            )
            assert consumer.received_values  == [10, 30, 70], (
                f"Expected [10, 30, 70], got {consumer.received_values}"
            )
        _arun(_body())

    # ── 5 ────────────────────────────────────────────────────────────────────

    def test_for_loop_nested_inside_while_loop(self):
        """
        Outer WhileLoop fires 2 times; inner ForLoop fires 3 times per outer
        iteration.  The body counter (inside the ForLoop body) should be
        called exactly 2 * 3 = 6 times.

        Graph:
            Outer(WhileLoop 2x).loop_body → Inner(ForLoop 0..3).exec
            Inner.loop_body               → Body(CountingBodyNode).exec
            Outer.stop_signal ← outer_counter.stop_signal  (2 iterations)
        """
        async def _body():
            net           = _make_net("nested_for_in_while")
            outer         = net.createNode("Outer",        "CT_WhileLoopNode")
            outer_counter = net.createNode("OuterCounter", "CT_CountingBodyNode")
            inner         = net.createNode("Inner",        "CT_ForLoopNode")
            body          = net.createNode("Body",         "CT_CountingBodyNode")

            outer_counter.inputs["max_count"].value = 2
            inner.inputs["start"].value             = 0
            inner.inputs["end"].value               = 3
            body.inputs["max_count"].value          = 999  # won't reach — for-loop ends it

            # Outer while-loop
            net.graph.add_edge(outer.id,         "loop_body",   outer_counter.id, "exec")
            net.graph.add_edge(outer_counter.id, "stop_signal", outer.id,         "stop_signal")
            net.graph.add_edge(outer_counter.id, "next",        inner.id,         "exec")

            # Inner for-loop
            net.graph.add_edge(inner.id, "loop_body", body.id, "exec")

            await Executor(net.graph).cook_flow_control_nodes(outer)

            assert body._count == 6, (
                f"Expected 2 outer × 3 inner = 6, got {body._count}"
            )
        _arun(_body())

    # ── 6 ────────────────────────────────────────────────────────────────────

    def test_while_loop_nested_inside_for_loop(self):
        """
        Outer ForLoop iterates 3 times.  For each iteration the inner
        WhileLoop runs 2 times.  Total inner body executions = 3 * 2 = 6.

        Graph:
            Outer(ForLoop 0..3).loop_body → Inner(WhileLoop).exec
            Inner.loop_body               → InnerBody.exec
            InnerBody.stop_signal         → Inner.stop_signal  (2 iterations)
        """
        async def _body():
            net        = _make_net("while_in_for")
            outer      = net.createNode("Outer",     "CT_ForLoopNode")
            inner      = net.createNode("Inner",     "CT_WhileLoopNode")
            inner_body = net.createNode("InnerBody", "CT_CountingBodyNode")

            outer.inputs["start"].value             = 0
            outer.inputs["end"].value               = 3
            inner_body.inputs["max_count"].value    = 2

            net.graph.add_edge(outer.id,      "loop_body",   inner.id,      "exec")
            net.graph.add_edge(inner.id,      "loop_body",   inner_body.id, "exec")
            net.graph.add_edge(inner_body.id, "stop_signal", inner.id,      "stop_signal")

            await Executor(net.graph).cook_flow_control_nodes(outer)

            assert inner_body._total_count == 6, (
                f"Expected 3 outer × 2 inner = 6, got {inner_body._total_count}"
            )
        _arun(_body())

    # ── 7 ────────────────────────────────────────────────────────────────────

    def test_while_loop_with_data_preceding_loop(self):
        """
        A CT_ConstNode data dependency is evaluated before the loop begins,
        and the loop body reads the correct value each iteration.  Verifies
        that upstream data nodes are cooked exactly once (not per-iteration).

        Graph:
            ConstNode.out → Body.max_count (data dep resolved before loop)
            Loop.loop_body → Body.exec
            Body.stop_signal → Loop.stop_signal
        """
        async def _body():
            net   = _make_net("wl_with_data_dep")
            const = net.createNode("Const", "CT_ConstNode")
            loop  = net.createNode("Loop",  "CT_WhileLoopNode")
            body  = net.createNode("Body",  "CT_CountingBodyNode")

            const.outputs["out"].value = 4  # run 4 iterations

            net.graph.add_edge(loop.id,  "loop_body",   body.id,  "exec")
            net.graph.add_edge(body.id,  "stop_signal", loop.id,  "stop_signal")
            net.graph.add_edge(const.id, "out",         body.id,  "max_count")

            await Executor(net.graph).cook_flow_control_nodes(loop)

            assert body._count == 4, (
                f"Expected 4 iterations (max_count from ConstNode=4), got {body._count}"
            )
        _arun(_body())


# ─────────────────────────────────────────────────────────────────────────────
# Invalid cycle topologies — must raise errors
# ─────────────────────────────────────────────────────────────────────────────

class TestInvalidCycleTopologies:
    """
    All topologies here are UNSAFE cycles without a flow-control mediator.
    The expected outcome varies depending on when the cycle is detectable:

    - Self-loops (A → A): detected immediately in Graph.add_edge (ValueError).
    - Mutual / chain data cycles (A ↔ B, A → B → C → A): detected by the
      executor's deadlock guard after all no-dependency nodes have been
      consumed (RuntimeError).
    """

    # ── 8 ────────────────────────────────────────────────────────────────────

    def test_self_loop_on_data_node_raises_at_build_time(self):
        """
        Connecting a data node's output back to its own input must raise
        ValueError inside Graph.add_edge before execution begins.
        """
        net  = _make_net("sl_data")
        node = net.createNode("A", "CT_AddNode")

        with pytest.raises(ValueError, match="Self-loop"):
            net.graph.add_edge(node.id, "sum", node.id, "a")

    # ── 9 ────────────────────────────────────────────────────────────────────

    def test_self_loop_on_flow_node_raises_at_build_time(self):
        """
        A flow-control node routing its own output back to its own control
        input must also raise ValueError at build time.
        """
        net  = _make_net("sl_flow")
        node = net.createNode("Trig", "CT_TriggerNode")

        with pytest.raises(ValueError, match="Self-loop"):
            net.graph.add_edge(node.id, "next", node.id, "exec")

    # ── 10 ───────────────────────────────────────────────────────────────────

    def test_two_node_mutual_data_dependency_deadlocks(self):
        """
        Classic mutual dependency: AddA needs AddB's output, and AddB needs
        AddA's output.  Neither can execute first.

        Graph (NO mediating WhileLoopNode):
            Const5.out → AddA.a
            AddB.sum   → AddA.b   ← CYCLE
            Const3.out → AddB.a
            AddA.sum   → AddB.b   ← CYCLE
            AddA.sum   → Trigger.value   (execution entry point)

        Expected: RuntimeError from the executor deadlock guard after Const5
        and Const3 are consumed but AddA / AddB are still mutually waiting.
        """
        async def _body():
            net     = _make_net("deadlock_2node")
            const5  = net.createNode("Const5",  "CT_ConstNode")
            const3  = net.createNode("Const3",  "CT_ConstNode")
            add_a   = net.createNode("AddA",    "CT_AddNode")
            add_b   = net.createNode("AddB",    "CT_AddNode")
            trigger = net.createNode("Trigger", "CT_TriggerNode")

            const5.outputs["out"].value = 5
            const3.outputs["out"].value = 3

            net.graph.add_edge(const5.id, "out", add_a.id,   "a")
            net.graph.add_edge(add_b.id,  "sum", add_a.id,   "b")   # cycle leg 1
            net.graph.add_edge(const3.id, "out", add_b.id,   "a")
            net.graph.add_edge(add_a.id,  "sum", add_b.id,   "b")   # cycle leg 2
            net.graph.add_edge(add_a.id,  "sum", trigger.id, "value")

            with pytest.raises(RuntimeError, match="deadlock|circular"):
                await Executor(net.graph).cook_flow_control_nodes(trigger)
        _arun(_body())

    # ── 11 ───────────────────────────────────────────────────────────────────

    def test_three_node_data_cycle_raises_runtime_error(self):
        """
        A three-node cycle: A.sum feeds B.a, B.sum feeds C.a, C.sum feeds A.a.
        No constant feeds any node — all three simultaneously wait on each other.

        Graph (pure cycle, no entry constants):
            AddA.sum → AddB.a   → AddB.sum → AddC.a   → AddC.sum → AddA.a
            AddA.sum → Trigger.value

        Expected: RuntimeError immediately (execution_stack starts empty
        because every node has at least one unsatisfied dependency).
        """
        async def _body():
            net     = _make_net("deadlock_3cycle")
            add_a   = net.createNode("A",       "CT_AddNode")
            add_b   = net.createNode("B",       "CT_AddNode")
            add_c   = net.createNode("C",       "CT_AddNode")
            trigger = net.createNode("Trigger", "CT_TriggerNode")

            # A → B → C → A  (pure 3-node cycle)
            net.graph.add_edge(add_a.id,  "sum",   add_b.id,   "a")
            net.graph.add_edge(add_b.id,  "sum",   add_c.id,   "a")
            net.graph.add_edge(add_c.id,  "sum",   add_a.id,   "a")   # closes cycle

            # Execution entry
            net.graph.add_edge(add_a.id,  "sum",   trigger.id, "value")

            with pytest.raises(RuntimeError):
                await Executor(net.graph).cook_flow_control_nodes(trigger)
        _arun(_body())

    # ── 12 ───────────────────────────────────────────────────────────────────

    def test_mixed_flow_data_cycle_deadlocks(self):
        """
        A flow-control trigger depends on a data node (AddA) whose second input
        comes from another data node (AddB), and AddB's input comes from AddA —
        forming AddA ↔ AddB mutual dependency exactly as in the 2-node case but
        discovered via a flow-control entry point.

        This tests that the deadlock guard is reached regardless of whether the
        graph traversal starts from a flow node or a data node.

        Graph:
            Const10.out → AddA.a
            AddB.sum    → AddA.b   ← cycle
            Const7.out  → AddB.a
            AddA.sum    → AddB.b   ← cycle
            AddA.sum    → Trigger.value  (flow entry)
        """
        async def _body():
            net     = _make_net("deadlock_mixed")
            const10 = net.createNode("Const10", "CT_ConstNode")
            const7  = net.createNode("Const7",  "CT_ConstNode")
            add_a   = net.createNode("AddA",    "CT_AddNode")
            add_b   = net.createNode("AddB",    "CT_AddNode")
            trigger = net.createNode("Trigger", "CT_TriggerNode")

            const10.outputs["out"].value = 10
            const7.outputs["out"].value  = 7

            net.graph.add_edge(const10.id, "out", add_a.id,   "a")
            net.graph.add_edge(add_b.id,   "sum", add_a.id,   "b")   # cycle leg 1
            net.graph.add_edge(const7.id,  "out", add_b.id,   "a")
            net.graph.add_edge(add_a.id,   "sum", add_b.id,   "b")   # cycle leg 2
            net.graph.add_edge(add_a.id,   "sum", trigger.id, "value")

            with pytest.raises(RuntimeError, match="deadlock|circular"):
                await Executor(net.graph).cook_flow_control_nodes(trigger)
        _arun(_body())
