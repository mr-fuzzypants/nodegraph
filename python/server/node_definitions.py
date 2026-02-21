"""
Demo node types — Python port of server/src/nodeDefinitions.ts.

Import this module once as a side-effect (e.g. from state.py) to register all
node types with the Node registry so they can be instantiated by name.

Guard against double-registration so pytest test-isolation still works: if a
test module (or the test run order) has already registered the same key, we
skip it rather than raising.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from nodegraph.python.core.Executor import ExecCommand, ExecutionResult
from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodePort import (
    InputControlPort,
    InputDataPort,
    OutputControlPort,
    OutputDataPort,
)
from nodegraph.python.core.Types import ValueType


# ---------------------------------------------------------------------------
# Registration helper — skips silently if type is already registered
# ---------------------------------------------------------------------------

def _safe_register(type_name: str):
    """Decorator that registers *cls* only when *type_name* is not yet in the registry."""
    def decorator(cls):
        if type_name not in Node._node_registry:
            Node._node_registry[type_name] = cls
        return cls
    return decorator


# ── ConstantNode ─────────────────────────────────────────────────────────────

@_safe_register("ConstantNode")
class ConstantNode(Node):
    def __init__(self, name: str, type: str = "ConstantNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.outputs["out"] = OutputDataPort(self.id, "out", ValueType.INT)
        self.outputs["out"].value = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["out"] = self.outputs["out"].value
        return result


# ── AddNode ──────────────────────────────────────────────────────────────────

@_safe_register("AddNode")
class AddNode(Node):
    def __init__(self, name: str, type: str = "AddNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["a"] = InputDataPort(self.id, "a", ValueType.INT)
        self.inputs["b"] = InputDataPort(self.id, "b", ValueType.INT)
        self.outputs["sum"] = OutputDataPort(self.id, "sum", ValueType.INT)

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}
        a = ctx_data.get("a", self.inputs["a"].value) or 0
        b = ctx_data.get("b", self.inputs["b"].value) or 0
        total = a + b
        self.outputs["sum"].value = total
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["sum"] = total
        return result


# ── PrintNode ─────────────────────────────────────────────────────────────────

@_safe_register("PrintNode")
class PrintNode(Node):
    def __init__(self, name: str, type: str = "PrintNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self.inputs["exec"] = InputControlPort(self.id, "exec")
        self.inputs["value"] = InputDataPort(self.id, "value", ValueType.ANY)
        self.outputs["next"] = OutputControlPort(self.id, "next")

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}
        val = ctx_data.get("value", self.inputs["value"].value)
        print("*************")
        print(f"[PrintNode '{self.name}'] value =", val)
        print("*************")
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.control_outputs["next"] = True
        return result


# ── BranchNode ───────────────────────────────────────────────────────────────

@_safe_register("BranchNode")
class BranchNode(Node):
    def __init__(self, name: str, type: str = "BranchNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self.inputs["exec"] = InputControlPort(self.id, "exec")
        self.inputs["condition"] = InputDataPort(self.id, "condition", ValueType.BOOL)
        self.outputs["true_out"] = OutputControlPort(self.id, "true_out")
        self.outputs["false_out"] = OutputControlPort(self.id, "false_out")

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}
        cond = bool(ctx_data.get("condition", self.inputs["condition"].value))
        result = ExecutionResult(ExecCommand.CONTINUE)
        if cond:
            result.control_outputs["true_out"] = True
            result.control_outputs["false_out"] = False
        else:
            result.control_outputs["true_out"] = False
            result.control_outputs["false_out"] = True
        return result


# ── ForLoopNode ─────────────────────────────────────────────────────────────

@_safe_register("ForLoopNode")
class ForLoopNode(Node):
    def __init__(self, name: str, type: str = "ForLoopNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self._loop_index: int = 0
        self._loop_active: bool = False

        self.inputs["exec"] = InputControlPort(self.id, "exec")
        self.inputs["start"] = InputDataPort(self.id, "start", ValueType.INT)
        self.inputs["end"] = InputDataPort(self.id, "end", ValueType.INT)
        self.outputs["loop_body"] = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"] = OutputControlPort(self.id, "completed")
        self.outputs["index"] = OutputDataPort(self.id, "index", ValueType.INT)

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}
        start: int = int(ctx_data.get("start", self.inputs["start"].value) or 0)
        end: int = int(ctx_data.get("end", self.inputs["end"].value) or 0)

        if not self._loop_active:
            self._loop_index = start
            self._loop_active = True

        if self._loop_index < end:
            idx = self._loop_index
            self._loop_index += 1
            self.outputs["index"].value = idx
            result = ExecutionResult(ExecCommand.LOOP_AGAIN)
            result.data_outputs["index"] = idx
            result.control_outputs["loop_body"] = True
            result.control_outputs["completed"] = False
            return result
        else:
            self._loop_index = start
            self._loop_active = False
            result = ExecutionResult(ExecCommand.COMPLETED)
            result.control_outputs["completed"] = True
            result.control_outputs["loop_body"] = False
            return result


# ── ForEachNode ─────────────────────────────────────────────────────────────
# Iterates over each element of a list, one executor call per element.
# Mirrors ForLoopNode's LOOP_AGAIN / COMPLETED pattern but operates on
# arbitrary Python lists rather than integer ranges.

@_safe_register("ForEachNode")
class ForEachNode(Node):
    """
    Ports
    -----
    Control in  : exec
    Data in     : items (list of any)
    Control out : loop_body  — fires once per element (LOOP_AGAIN)
                  completed  — fires when the list is exhausted (COMPLETED)
    Data out    : item   — current element
                  index  — 0-based position
                  total  — len(items), constant for the whole loop
    """

    def __init__(self, name: str, type: str = "ForEachNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True

        self._items:  list = []
        self._index:  int  = 0
        self._total:  int  = 0
        self._active: bool = False

        self.inputs["exec"]       = InputControlPort(self.id, "exec")
        self.inputs["items"]      = InputDataPort(self.id, "items", ValueType.ANY)

        self.outputs["loop_body"] = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"] = OutputControlPort(self.id, "completed")
        self.outputs["item"]      = OutputDataPort(self.id, "item",  ValueType.ANY)
        self.outputs["index"]     = OutputDataPort(self.id, "index", ValueType.INT)
        self.outputs["total"]     = OutputDataPort(self.id, "total", ValueType.INT)

        self.inputs["items"].value  = []
        self.outputs["item"].value  = None
        self.outputs["index"].value = 0
        self.outputs["total"].value = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}

        if not self._active:
            raw = ctx_data.get("items", self.inputs["items"].value)
            if raw is None:
                self._items = []
            elif isinstance(raw, list):
                self._items = list(raw)
            else:
                self._items = [raw]  # wrap plain scalar in a list
            self._total  = len(self._items)
            self._index  = 0
            self._active = True

            # Empty list → skip directly to COMPLETED
            if self._total == 0:
                self._active = False
                result = ExecutionResult(ExecCommand.COMPLETED)
                result.control_outputs["completed"] = True
                result.control_outputs["loop_body"]  = False
                return result

        if self._index < self._total:
            item = self._items[self._index]
            idx  = self._index
            self._index += 1

            self.outputs["item"].value  = item
            self.outputs["index"].value = idx
            self.outputs["total"].value = self._total

            result = ExecutionResult(ExecCommand.LOOP_AGAIN)
            result.data_outputs["item"]  = item
            result.data_outputs["index"] = idx
            result.data_outputs["total"] = self._total
            result.control_outputs["loop_body"] = True
            result.control_outputs["completed"] = False
            return result
        else:
            self._active = False
            self._items  = []
            self._index  = 0
            result = ExecutionResult(ExecCommand.COMPLETED)
            result.control_outputs["completed"] = True
            result.control_outputs["loop_body"]  = False
            return result


# ── AccumulatorNode ────────────────────────────────────────────────────────

@_safe_register("AccumulatorNode")
class AccumulatorNode(Node):
    def __init__(self, name: str, type: str = "AccumulatorNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self.call_count: int = 0
        self.last_value = None
        self.values: list = []

        self.inputs["exec"] = InputControlPort(self.id, "exec")
        self.inputs["val"] = InputDataPort(self.id, "val", ValueType.ANY)
        self.outputs["next"] = OutputControlPort(self.id, "next")

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}
        val = ctx_data.get("val", self.inputs["val"].value)
        self.call_count += 1
        if val is not None:
            self.last_value = val
            self.values.append(val)
        print(f"[AccumulatorNode '{self.name}'] call #{self.call_count}, val={val}")
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.control_outputs["next"] = True
        return result


# ── MultiplyNode ─────────────────────────────────────────────────────────────

@_safe_register("MultiplyNode")
class MultiplyNode(Node):
    def __init__(self, name: str, type: str = "MultiplyNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["a"] = InputDataPort(self.id, "a", ValueType.INT)
        self.inputs["b"] = InputDataPort(self.id, "b", ValueType.INT)
        self.outputs["product"] = OutputDataPort(self.id, "product", ValueType.INT)

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}
        a = int(ctx_data.get("a", self.inputs["a"].value) or 0)
        b = int(ctx_data.get("b", self.inputs["b"].value) or 1)
        product = a * b
        self.outputs["product"].value = product
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["product"] = product
        return result


# ── VectorNode ────────────────────────────────────────────────────────────────

@_safe_register("VectorNode")
class VectorNode(Node):
    def __init__(self, name: str, type: str = "VectorNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["x"] = InputDataPort(self.id, "x", ValueType.FLOAT)
        self.inputs["y"] = InputDataPort(self.id, "y", ValueType.FLOAT)
        self.inputs["z"] = InputDataPort(self.id, "z", ValueType.FLOAT)
        self.outputs["vec"] = OutputDataPort(self.id, "vec", ValueType.VECTOR)
        self.inputs["x"].value = 0.0
        self.inputs["y"].value = 0.0
        self.inputs["z"].value = 0.0
        self.outputs["vec"].value = [0.0, 0.0, 0.0]

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}
        x = float(ctx_data.get("x", self.inputs["x"].value) or 0)
        y = float(ctx_data.get("y", self.inputs["y"].value) or 0)
        z = float(ctx_data.get("z", self.inputs["z"].value) or 0)
        vec = [x, y, z]
        self.outputs["vec"].value = vec
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["vec"] = vec
        return result


# ── StepPrinterNode ──────────────────────────────────────────────────────────
# Flow-control companion to ToolAgentStreamNode.
# Wired to loop_body — fires once per tool_call / tool_result step.
# Prints a formatted line for each step type.

@_safe_register("StepPrinterNode")
class StepPrinterNode(Node):
    def __init__(self, name: str, type: str = "StepPrinterNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self.inputs["exec"]         = InputControlPort(self.id, "exec")
        self.inputs["step_type"]    = InputDataPort(self.id, "step_type",    ValueType.STRING)
        self.inputs["step_content"] = InputDataPort(self.id, "step_content", ValueType.STRING)
        self.inputs["tool_name"]    = InputDataPort(self.id, "tool_name",    ValueType.STRING)
        self.outputs["next"]        = OutputControlPort(self.id, "next")

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx     = (executionContext or {}).get("data_inputs", {}) if executionContext else {}
        stype   = ctx.get("step_type",    self.inputs["step_type"].value)    or ""
        content = ctx.get("step_content", self.inputs["step_content"].value) or ""
        tname   = ctx.get("tool_name",    self.inputs["tool_name"].value)    or ""

        if stype == "tool_call":
            print(f"  → {tname}({content})", flush=True)
        elif stype == "tool_result":
            print(f"  ← {content}", flush=True)
        else:
            print(f"  [{stype}] {content}", flush=True)

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.control_outputs["next"] = True
        return result


# ── DotProductNode ──────────────────────────────────────────────────────────

@_safe_register("DotProductNode")
class DotProductNode(Node):
    def __init__(self, name: str, type: str = "DotProductNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["vec_a"] = InputDataPort(self.id, "vec_a", ValueType.VECTOR)
        self.inputs["vec_b"] = InputDataPort(self.id, "vec_b", ValueType.VECTOR)
        self.outputs["result"] = OutputDataPort(self.id, "result", ValueType.FLOAT)
        self.outputs["result"].value = 0.0

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data = executionContext.get("data_inputs", {}) if executionContext else {}
        a = ctx_data.get("vec_a", self.inputs["vec_a"].value) or []
        b = ctx_data.get("vec_b", self.inputs["vec_b"].value) or []
        dot = sum((ai or 0) * (bi or 0) for ai, bi in zip(a, b))
        self.outputs["result"].value = dot
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["result"] = dot
        return result


# ── LangChain node types ──────────────────────────────────────────────────────
# Imported as a side-effect so the server starts cleanly even when the
# langchain packages are not yet installed.
try:
    import nodegraph.python.server.langchain_nodes  # noqa: F401
except ImportError as _lc_err:
    print(f"[node_definitions] LangChain nodes skipped ({_lc_err})")
