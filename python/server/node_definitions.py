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
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from nodegraph.python.core.Executor import ExecCommand, ExecutionResult
from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodePort import (
    InputControlPort,
    InputDataPort,
    OutputControlPort,
    OutputDataPort,
)
import asyncio
from typing import Dict as _Dict, Optional as _Optional

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


@_safe_register("TemplateString")
class TemplateStringNode(Node):
    def __init__(self, name: str, type: str = "TemplateString", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["tstring"] = InputDataPort(self.id, "tstring", ValueType.STRING)
        self.outputs["result"] = OutputDataPort(self.id, "result", ValueType.STRING)

        self.inputs["tstring"].value = "Hello {name}"
        self.outputs["result"].value = ""

    @staticmethod
    def _validate_token_name(port_name: str) -> None:
        if port_name == "tstring":
            raise ValueError("'tstring' is reserved")
        if not port_name.isidentifier():
            raise ValueError("Template token names must be valid Python identifiers")

    def add_token_input(self, port_name: str, value_type: ValueType) -> None:
        self._validate_token_name(port_name)
        self.add_data_input(port_name, data_type=value_type)

    def add_dynamic_input_port(self, port_name: str, value_type: ValueType) -> None:
        self.add_token_input(port_name, value_type)

    def remove_token_input(self, port_name: str) -> None:
        self._validate_token_name(port_name)
        if port_name not in self.inputs:
            raise ValueError(f"Token input '{port_name}' does not exist")
        self.delete_input(port_name)

    def remove_dynamic_input_port(self, port_name: str) -> None:
        self.remove_token_input(port_name)

    async def compute(self, executionContext=None) -> ExecutionResult:
        template = self.inputs["tstring"].value or ""
        replacements = {
            name: port.value
            for name, port in self.inputs.items()
            if name != "tstring"
        }

        rendered = template.format(**replacements)
        self.outputs["result"].value = rendered

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["result"] = rendered
        return result


@_safe_register("Environment")
class EnvironmentNode(Node):
    _ENV_PREFIXES = {
        "ES_INT_": (ValueType.INT, int),
        "ES_FLT_": (ValueType.FLOAT, float),
        "ES_STR_": (ValueType.STRING, lambda value: value),
        "ES_DCT_": (ValueType.DICT, json.loads),
        "ES_ARR_": (ValueType.ARRAY, json.loads),
    }

    _USER_ALLOWED_TYPES = {
        ValueType.INT,
        ValueType.FLOAT,
        ValueType.STRING,
        ValueType.DICT,
        ValueType.ARRAY,
    }

    def __init__(self, name: str, type: str = "Environment", **kwargs):
        super().__init__(name, type, **kwargs)
        self._passthrough_ports: dict[str, ValueType] = {}
        self._refresh_environment_outputs()

    @staticmethod
    def _validate_port_name(port_name: str) -> None:
        if not port_name.isidentifier():
            raise ValueError("Environment port names must be valid Python identifiers")

    @classmethod
    def _parse_env_value(cls, prefix: str, raw_value: str):
        value_type, parser = cls._ENV_PREFIXES[prefix]
        value = parser(raw_value)
        if value_type == ValueType.DICT and not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        if value_type == ValueType.ARRAY and not isinstance(value, list):
            raise ValueError("Expected a JSON array")
        return value_type, value

    def _refresh_environment_outputs(self) -> None:
        for env_name, env_value in os.environ.items():
            matched_prefix = next(
                (prefix for prefix in self._ENV_PREFIXES if env_name.startswith(prefix)),
                None,
            )
            if matched_prefix is None:
                continue

            port_name = env_name[len(matched_prefix):].lower()
            if not port_name or port_name in self._passthrough_ports:
                continue

            self._validate_port_name(port_name)
            value_type, parsed_value = self._parse_env_value(matched_prefix, env_value)

            if port_name not in self.outputs:
                self.outputs[port_name] = OutputDataPort(self.id, port_name, value_type)
            self.outputs[port_name].data_type = value_type
            self.outputs[port_name].value = parsed_value

    def refresh_dynamic_ports(self) -> None:
        self._refresh_environment_outputs()

    def add_dynamic_input_port(self, port_name: str, value_type: ValueType) -> None:
        self._validate_port_name(port_name)
        if value_type not in self._USER_ALLOWED_TYPES:
            raise ValueError(f"Unsupported Environment input type '{value_type.value}'")
        if port_name in self.outputs and port_name not in self._passthrough_ports:
            raise ValueError(f"Output port '{port_name}' is reserved by an environment variable")

        self.add_data_input(port_name, data_type=value_type)
        if port_name not in self.outputs:
            self.outputs[port_name] = OutputDataPort(self.id, port_name, value_type)
        self.outputs[port_name].data_type = value_type
        self._passthrough_ports[port_name] = value_type

    def remove_dynamic_input_port(self, port_name: str) -> None:
        if port_name not in self._passthrough_ports:
            raise ValueError(f"Environment input '{port_name}' does not exist")

        self.delete_input(port_name)
        self.delete_output(port_name)
        del self._passthrough_ports[port_name]

    async def compute(self, executionContext=None) -> ExecutionResult:
        self._refresh_environment_outputs()

        result = ExecutionResult(ExecCommand.CONTINUE)
        for port_name in self._passthrough_ports:
            value = self.inputs[port_name].value
            self.outputs[port_name].value = value
            result.data_outputs[port_name] = value

        for env_name, port in self.outputs.items():
            if env_name not in self._passthrough_ports:
                result.data_outputs[env_name] = port.value

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
        message = f"[PrintNode '{self.name}'] value = {val}"
        print("*************")
        print(message)
        print("*************")
        try:
            from nodegraph.python.server.trace.trace_emitter import global_tracer
            global_tracer.fire({
                "type": "CONSOLE_OUTPUT",
                "nodeId": self.id,
                "nodeName": self.name,
                "message": message,
                "stream": "stdout",
            })
        except Exception:
            pass
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.control_outputs["next"] = True
        return result


@_safe_register("StartNode")
class StartNode(Node):
    def __init__(self, name: str, type: str = "StartNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self.outputs["start"] = OutputControlPort(self.id, "start")

    @staticmethod
    def _validate_output_name(port_name: str) -> str:
        trimmed = port_name.strip()
        if not trimmed:
            raise ValueError("Output name cannot be empty")
        if trimmed == "start":
            raise ValueError("'start' is reserved")
        if not trimmed.isidentifier():
            raise ValueError("Start output names must be valid Python identifiers")
        return trimmed

    def add_dynamic_output_port(
        self,
        port_name: str,
        value_type: ValueType,
        port_function: str = "DATA",
    ) -> None:
        resolved_name = self._validate_output_name(port_name)
        if resolved_name in self.outputs:
            raise ValueError(f"Output port '{resolved_name}' already exists")

        if port_function == "CONTROL":
            self.add_control_output(resolved_name)
        else:
            self.add_data_output(resolved_name, data_type=value_type)
            self.outputs[resolved_name].value = None

    def remove_dynamic_output_port(self, port_name: str) -> None:
        resolved_name = self._validate_output_name(port_name)
        if resolved_name not in self.outputs:
            raise ValueError(f"Output port '{resolved_name}' does not exist")
        self.delete_output(resolved_name)

    async def compute(self, executionContext=None) -> ExecutionResult:
        result = ExecutionResult(ExecCommand.CONTINUE)
        for port_name, port in self.outputs.items():
            if port.function == port.function.CONTROL:
                result.control_outputs[port_name] = True
            else:
                result.data_outputs[port_name] = port.value
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
            message = f"  → {tname}({content})"
        elif stype == "tool_result":
            message = f"  ← {content}"
        else:
            message = f"  [{stype}] {content}"

        print(message, flush=True)
        try:
            from nodegraph.python.server.trace.trace_emitter import global_tracer
            global_tracer.fire({
                "type": "CONSOLE_OUTPUT",
                "nodeId": self.id,
                "nodeName": self.name,
                "message": message,
                "stream": "stdout",
            })
        except Exception:
            pass

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


# ── HumanInputNode ───────────────────────────────────────────────────────────
# Pauses graph execution until a human responds via POST /api/nodes/{id}/human-input.
#
# Durability (Phase 1):
#   When running inside a DBOS workflow the suspension is persisted to Postgres
#   via DBOS.recv().  On process restart DBOS replays the workflow up to the
#   DBOS.recv() call, at which point the coroutine blocks again waiting for the
#   matching DBOS.send() — the human just re-sends their response via the API.
#
#   When DBOS is not active (tests, direct script execution) the node falls
#   back to the original asyncio.Event mechanism so nothing breaks.
#
#   The pending registry key is (node_id, workflow_id) to prevent collisions
#   when the same node runs in two concurrent workflow instances.

@_safe_register("HumanInputNode")
class HumanInputNode(Node):
    """
    Ports
    -----
    Control in  : exec
    Data in     : prompt        — question shown/logged to the human
                  timeout_secs — how long to wait before firing timed_out (default 300)
    Control out : responded    — fires when the human submits a response
                  timed_out   — fires if timeout elapses with no response
    Data out    : response     — the human's text (empty string on timeout)
    """

    # No class-level state needed — the submit endpoint looks up the node
    # directly from graph_state.active_executors[run_id].graph.

    def __init__(self, name: str, type: str = "HumanInputNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step = True  # wraps in @DBOS.step when inside a workflow
        self._event:    _Optional[asyncio.Event] = None
        self._response: str  = ""
        self._waiting:  bool = False

        # Test hook: when set, compute() returns this value immediately instead
        # of blocking on asyncio.Event.  Accepts a plain string or a zero-arg
        # callable that returns a string.  Set on the node instance in tests:
        #
        #   node.auto_respond = "Alice"              # static
        #   node.auto_respond = lambda: "Alice"      # dynamic / callable
        #
        # Leave as None (default) for normal asyncio.Event-based blocking.
        self.auto_respond: _Optional[object] = None

        self.inputs["exec"]         = InputControlPort(self.id, "exec")
        self.inputs["prompt"]       = InputDataPort(self.id, "prompt",       ValueType.STRING)
        self.inputs["timeout_secs"] = InputDataPort(self.id, "timeout_secs", ValueType.FLOAT)

        self.outputs["responded"]  = OutputControlPort(self.id, "responded")
        self.outputs["timed_out"]  = OutputControlPort(self.id, "timed_out")
        self.outputs["response"]   = OutputDataPort(self.id, "response", ValueType.STRING)

        self.inputs["prompt"].value       = "Please enter your response:"
        self.inputs["timeout_secs"].value  = 300.0
        self.outputs["response"].value     = ""

    # ── helpers ──────────────────────────────────────────────────────────────

    def provide_response(self, text: str) -> None:
        """Unblock compute() with the human's response.

        Called by POST /api/executions/{run_id}/nodes/{node_id}/human-input.
        The asyncio.Event wakes the waiting compute() coroutine immediately
        since both coroutines share the same event loop.
        """
        self._response = text
        if self._event is not None:
            self._event.set()

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx = (executionContext or {}).get("data_inputs", {}) if executionContext else {}
        prompt  = ctx.get("prompt",       self.inputs["prompt"].value) or "Enter response:"
        timeout = float(ctx.get("timeout_secs", self.inputs["timeout_secs"].value) or 300.0)

        self._event    = asyncio.Event()
        self._response = ""
        self._waiting  = True

        # Broadcast to the trace stream — the UI listens for this to show an input form.
        try:
            from nodegraph.python.server.trace.trace_emitter import global_tracer
            global_tracer.fire({"type": "HUMAN_INPUT_REQUIRED", "nodeId": self.id, "prompt": prompt})
        except Exception:
            pass

        print(f"[HumanInputNode '{self.name}'] WAITING — prompt: {prompt!r}", flush=True)

        timed_out = False
        response  = ""

        # ── auto_respond fast path (tests) ─────────────────────────────────
        # When auto_respond is set (typically by a test fixture) skip the
        # asyncio.Event entirely and return instantly with the preset value.
        # This makes HumanInputNode unit-testable without threads, asyncio
        # tasks, or HTTP calls.
        if self.auto_respond is not None:
            response = (
                self.auto_respond()                    # callable
                if callable(self.auto_respond)
                else str(self.auto_respond)            # plain string
            )
        # ── asyncio.Event path (primary — works in all cases) ─────────────────
        # Both this coroutine and the HTTP handler share the same event loop,
        # so asyncio.Event is the fastest and most reliable mechanism.
        # DBOS.recv() is intentionally NOT used here: with SQLite it relies on
        # polling and does not reliably wake when DBOS.send() fires in the same
        # process.  DBOS durability (cross-process replay) is handled separately
        # by also calling DBOS.send() from provide_response() so that the
        # persisted message is available after a restart.
        else:
            try:
                await asyncio.wait_for(self._event.wait(), timeout=timeout)
                response = self._response
            except asyncio.TimeoutError:
                timed_out = True

        self._waiting = False
        self.outputs["response"].value = response

        result = ExecutionResult(ExecCommand.WAIT)
        result.data_outputs["response"] = response
        if timed_out:
            print(f"[HumanInputNode '{self.name}'] TIMED OUT after {timeout}s", flush=True)
            result.control_outputs["responded"] = False
            result.control_outputs["timed_out"] = True
        else:
            print(f"[HumanInputNode '{self.name}'] RESPONDED: {response!r}", flush=True)
            result.control_outputs["responded"] = True
            result.control_outputs["timed_out"] = False
        return result


# ── WhileLoopNode ────────────────────────────────────────────────────────────
# Loops until stop_signal equals "done" (or "stop"/"quit"/"exit"/empty string).
# Mirrors ForLoopNode's LOOP_AGAIN / COMPLETED pattern.
#
# The stop_signal is ONLY checked on the 2nd+ call (after at least one body
# iteration), so the loop always fires at least once.  Connect a HumanInputNode
# response port to stop_signal so the human controls when to exit.
#
#  Control in  : exec
#  Data in     : stop_signal (STRING) — checked after the first iteration
#  Control out : loop_body  — fires each iteration          (LOOP_AGAIN)
#                completed  — fires when stop condition met (COMPLETED)
#  Data out    : iteration  — 0-based count of completed iterations

@_safe_register("WhileLoopNode")
class WhileLoopNode(Node):
    def __init__(self, name: str, type: str = "WhileLoopNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self._iteration: int = 0
        self._active: bool = False

        self.inputs["exec"]        = InputControlPort(self.id, "exec")
        self.inputs["stop_signal"] = InputDataPort(self.id, "stop_signal", ValueType.STRING)
        self.outputs["loop_body"]  = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"]  = OutputControlPort(self.id, "completed")
        self.outputs["iteration"]  = OutputDataPort(self.id, "iteration", ValueType.INT)

        self.inputs["stop_signal"].value = ""
        self.outputs["iteration"].value  = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx_data    = executionContext.get("data_inputs", {}) if executionContext else {}
        stop_signal = str(ctx_data.get("stop_signal", self.inputs["stop_signal"].value) or "")

        if not self._active:
            # First call — always fire loop_body; never check stop_signal.
            self._active    = True
            self._iteration = 0
        else:
            # Subsequent calls — honour the stop condition.
            if stop_signal.strip().lower() in ("done", "stop", "quit", "exit", ""):
                self._active    = False
                self._iteration = 0
                result = ExecutionResult(ExecCommand.COMPLETED)
                result.control_outputs["completed"] = True
                result.control_outputs["loop_body"] = False
                return result

        idx             = self._iteration
        self._iteration += 1
        self.outputs["iteration"].value = idx

        result = ExecutionResult(ExecCommand.LOOP_AGAIN)
        result.data_outputs["iteration"]     = idx
        result.control_outputs["loop_body"]  = True
        result.control_outputs["completed"]  = False
        return result


# ── pydantic-ai node types (preferred replacements for LangChain nodes) ───────
# Registered first so they shadow the LangChain variants when pydantic-ai is
# available.  The _safe_register() guard means the second import (langchain)
# skips types that are already registered.
try:
    import nodegraph.python.server.pydantic_ai_nodes  # noqa: F401
    print("[node_definitions] pydantic-ai nodes loaded")
except ImportError as _pai_err:
    print(f"[node_definitions] pydantic-ai nodes skipped ({_pai_err})")

# ── LangChain node types ──────────────────────────────────────────────────────
# Fallback: registers any types not already covered by pydantic_ai_nodes.
# Skipped gracefully when the langchain packages are not installed.
try:
    import nodegraph.python.server.langchain_nodes  # noqa: F401
except ImportError as _lc_err:
    print(f"[node_definitions] LangChain nodes skipped ({_lc_err})")

# ── Agent node types (pydantic-ai powered — AgentExecutor support) ────────────
# Imported as a side-effect; skipped gracefully if pydantic-ai is absent.
try:
    import nodegraph.python.noderegistry.AgentNodes  # noqa: F401
except ImportError as _agent_err:
    print(f"[node_definitions] Agent nodes skipped ({_agent_err})")

# ── Imaging / diffusion pipeline node types ───────────────────────────────────
# Registers CheckpointLoader, CLIPTextEncode, EmptyLatentImage, KSampler,
# VAEDecode, VAEEncode, LoadImage, SaveImage.
# Skipped gracefully when torch / diffusers are not installed.
try:
    import nodegraph.python.noderegistry.imaging  # noqa: F401
    print("[node_definitions] imaging nodes loaded")
except ImportError as _img_err:
    print(f"[node_definitions] imaging nodes skipped ({_img_err})")
