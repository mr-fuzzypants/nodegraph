"""
NodeGraph Compiler v3 — JSON Deserialiser
==========================================
Converts a serialised graph JSON file (or dict) directly into an IRGraph,
bypassing the need for live node objects.

This module replaces compiler2/extractor.py for the JSON-based compilation
pathway.  The extractor requires live `Graph` objects; the deserialiser
requires only a JSON description.

Pipeline
--------
    graph.json  →  [deserialiser.json_to_ir]  →  IRGraph
    IRGraph     →  [compiler2.scheduler]       →  IRSchedule
    IRSchedule  →  [compiler3.emitter]         →  Python source str

JSON format
-----------
See python/compiler3/schema.py for the full schema definition.

Quick reference:

    {
      "graph_name": "streaming-agent-simple",
      "nodes": [
        {
          "id":   "node_001",
          "type": "ConstantNode",
          "name": "Task",
          "inputs":  { "value": "What is 123 * 456?" },
          "outputs": {}
        },
        ...
      ],
      "edges": [
        { "from_node": "node_001", "from_port": "out",
          "to_node":   "node_002", "to_port":   "task" },
        ...
      ]
    }

Port class inference
--------------------
The deserialiser resolves each port's class ("data" or "control") using the
PORT_SCHEMA registry (hardcoded per known node type).  For unknown node types
it falls back to a name-pattern heuristic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from nodegraph.python.compiler2.ir import IREdge, IRGraph, IRNode, IRPort


# ── Port schema registry ──────────────────────────────────────────────────────
#
# Maps type_name → {port_name → {direction, port_class, default_value?}}
#
# "direction" is "in" | "out"
# "port_class" is "data" | "control"
#
# This registry covers all node types registered in node_definitions.py and
# langchain_nodes.py.  Add new entries here when adding new compilable nodes.

_P = Dict[str, Dict[str, Any]]   # type alias for a port spec dict

PORT_SCHEMA: Dict[str, _P] = {

    "ConstantNode": {
        "out": {"direction": "out", "port_class": "data"},
    },

    "AddNode": {
        "a":   {"direction": "in",  "port_class": "data", "default": 0},
        "b":   {"direction": "in",  "port_class": "data", "default": 0},
        "sum": {"direction": "out", "port_class": "data"},
    },

    "MultiplyNode": {
        "a":       {"direction": "in",  "port_class": "data", "default": 0},
        "b":       {"direction": "in",  "port_class": "data", "default": 1},
        "product": {"direction": "out", "port_class": "data"},
    },

    "PrintNode": {
        "exec":  {"direction": "in",  "port_class": "control"},
        "value": {"direction": "in",  "port_class": "data"},
        "next":  {"direction": "out", "port_class": "control"},
    },

    "BranchNode": {
        "exec":      {"direction": "in",  "port_class": "control"},
        "condition": {"direction": "in",  "port_class": "data", "default": False},
        "true_out":  {"direction": "out", "port_class": "control"},
        "false_out": {"direction": "out", "port_class": "control"},
    },

    "ForLoopNode": {
        "exec":      {"direction": "in",  "port_class": "control"},
        "start":     {"direction": "in",  "port_class": "data", "default": 0},
        "end":       {"direction": "in",  "port_class": "data", "default": 0},
        "loop_body": {"direction": "out", "port_class": "control"},
        "completed": {"direction": "out", "port_class": "control"},
        "index":     {"direction": "out", "port_class": "data"},
    },

    "ForEachNode": {
        "exec":      {"direction": "in",  "port_class": "control"},
        "items":     {"direction": "in",  "port_class": "data", "default": []},
        "loop_body": {"direction": "out", "port_class": "control"},
        "completed": {"direction": "out", "port_class": "control"},
        "item":      {"direction": "out", "port_class": "data"},
        "index":     {"direction": "out", "port_class": "data", "default": 0},
        "total":     {"direction": "out", "port_class": "data", "default": 0},
    },

    "AccumulatorNode": {
        "exec": {"direction": "in",  "port_class": "control"},
        "val":  {"direction": "in",  "port_class": "data"},
        "next": {"direction": "out", "port_class": "control"},
    },

    "StepPrinterNode": {
        "exec":         {"direction": "in",  "port_class": "control"},
        "step_type":    {"direction": "in",  "port_class": "data", "default": ""},
        "step_content": {"direction": "in",  "port_class": "data", "default": ""},
        "tool_name":    {"direction": "in",  "port_class": "data", "default": ""},
        "next":         {"direction": "out", "port_class": "control"},
    },

    # ── LangChain / AI nodes ────────────────────────────────────────────────

    "ToolAgentNode": {
        "task":       {"direction": "in",  "port_class": "data", "default": ""},
        "tools":      {"direction": "in",  "port_class": "data",
                       "default": ["calculator", "word_count"]},
        "model":      {"direction": "in",  "port_class": "data", "default": "gpt-4o-mini"},
        "result":     {"direction": "out", "port_class": "data"},
        "tool_calls": {"direction": "out", "port_class": "data"},
        "steps":      {"direction": "out", "port_class": "data"},
    },

    "ToolAgentStreamNode": {
        "exec":         {"direction": "in",  "port_class": "control"},
        "task":         {"direction": "in",  "port_class": "data", "default": ""},
        "tools":        {"direction": "in",  "port_class": "data",
                         "default": ["calculator", "word_count"]},
        "model":        {"direction": "in",  "port_class": "data", "default": "gpt-4o-mini"},
        "loop_body":    {"direction": "out", "port_class": "control"},
        "completed":    {"direction": "out", "port_class": "control"},
        "step_type":    {"direction": "out", "port_class": "data", "default": ""},
        "step_content": {"direction": "out", "port_class": "data", "default": ""},
        "tool_name":    {"direction": "out", "port_class": "data", "default": ""},
        "step_count":   {"direction": "out", "port_class": "data", "default": 0},
        "result":       {"direction": "out", "port_class": "data", "default": ""},
    },

    "LLMNode": {
        "prompt":        {"direction": "in",  "port_class": "data", "default": ""},
        "system_prompt": {"direction": "in",  "port_class": "data",
                          "default": "You are a helpful assistant."},
        "model":         {"direction": "in",  "port_class": "data", "default": "gpt-4o-mini"},
        "temperature":   {"direction": "in",  "port_class": "data", "default": 0.7},
        "response":      {"direction": "out", "port_class": "data"},
        "model_used":    {"direction": "out", "port_class": "data"},
        "tokens_used":   {"direction": "out", "port_class": "data"},
    },

    "PromptTemplateNode": {
        "template":  {"direction": "in",  "port_class": "data",
                      "default": "Answer the following question: {question}"},
        "variables": {"direction": "in",  "port_class": "data", "default": {}},
        "prompt":    {"direction": "out", "port_class": "data"},
    },

    "VectorNode": {
        "x":   {"direction": "in",  "port_class": "data", "default": 0.0},
        "y":   {"direction": "in",  "port_class": "data", "default": 0.0},
        "z":   {"direction": "in",  "port_class": "data", "default": 0.0},
        "vec": {"direction": "out", "port_class": "data"},
    },

    "DotProductNode": {
        "vec_a":  {"direction": "in",  "port_class": "data", "default": []},
        "vec_b":  {"direction": "in",  "port_class": "data", "default": []},
        "result": {"direction": "out", "port_class": "data"},
    },
}


# ── Fallback heuristics for unknown node types ────────────────────────────────

_CONTROL_PORT_NAMES = frozenset({
    "exec", "next", "loop_body", "completed",
    "true_out", "false_out", "trigger", "done",
})


def _infer_port_class_from_name(port_name: str) -> str:
    """Heuristic: return 'control' for well-known control port names, else 'data'."""
    return "control" if port_name in _CONTROL_PORT_NAMES else "data"


# ── Exec-class inference ──────────────────────────────────────────────────────

def _infer_exec_class(type_name: str, out_port_names: List[str]) -> str:
    """
    Replicate extractor.py exec-class heuristic purely from port names.

    Works for both registered types (via PORT_SCHEMA) and unknown types.
    """
    schema = PORT_SCHEMA.get(type_name, {})
    is_flow = any(
        spec.get("port_class") == "control"
        for spec in schema.values()
    ) or any(
        _infer_port_class_from_name(p) == "control"
        for p in out_port_names
    )

    out_set = set(out_port_names)

    if not is_flow:
        return "constant" if not schema.get("inputs") else "data"

    if "loop_body" in out_set and "completed" in out_set:
        return "loop_again"
    if "true_out" in out_set and "false_out" in out_set:
        return "branch"
    return "passthrough"


# ── Core parsing ──────────────────────────────────────────────────────────────

def _parse_node(node_spec: Dict[str, Any]) -> IRNode:
    """Convert a JSON node dict → IRNode."""
    node_id   = node_spec["id"]
    type_name = node_spec["type"]
    name      = node_spec.get("name", type_name)
    json_inputs  = node_spec.get("inputs",  {})
    json_outputs = node_spec.get("outputs", {})

    schema = PORT_SCHEMA.get(type_name, {})

    # ── Build input ports ───────────────────────────────────────────────────

    input_ports: Dict[str, IRPort] = {}

    # Start from schema-defined ports so structure is complete even if JSON omits ports.
    for pname, pspec in schema.items():
        if pspec["direction"] != "in":
            continue
        # JSON "inputs" values take priority over schema defaults.
        value = json_inputs.get(pname, pspec.get("default"))
        input_ports[pname] = IRPort(
            name=pname,
            direction="in",
            port_class=pspec["port_class"],
            value=value,
        )

    # Add any extra input keys in the JSON that aren't in the schema.
    for pname, value in json_inputs.items():
        if pname not in input_ports:
            port_class = _infer_port_class_from_name(pname)
            input_ports[pname] = IRPort(
                name=pname,
                direction="in",
                port_class=port_class,
                value=value,
            )

    # ── Build output ports ──────────────────────────────────────────────────

    output_ports: Dict[str, IRPort] = {}

    for pname, pspec in schema.items():
        if pspec["direction"] != "out":
            continue
        value = json_outputs.get(pname, pspec.get("default"))
        output_ports[pname] = IRPort(
            name=pname,
            direction="out",
            port_class=pspec["port_class"],
            value=value,
        )

    # Extra output keys from JSON not in schema.
    for pname, value in json_outputs.items():
        if pname not in output_ports:
            port_class = _infer_port_class_from_name(pname)
            output_ports[pname] = IRPort(
                name=pname,
                direction="out",
                port_class=port_class,
                value=value,
            )

    # ── Exec class & is_flow_control ────────────────────────────────────────

    exec_class = _infer_exec_class(type_name, list(output_ports.keys()))
    is_flow    = any(p.port_class == "control" for p in output_ports.values())

    # ── Static output values (for ConstantNode etc.) ─────────────────────────
    # Mirror extractor.py: capture non-None data output values.
    static_outputs = {
        k: p.value
        for k, p in output_ports.items()
        if p.port_class == "data" and p.value is not None
    }

    # For ConstantNode the value is in "inputs.value" in JSON but needs to end
    # up in outputs["out"].value for the scheduler/emitter to find it.
    if type_name == "ConstantNode":
        constant_val = json_inputs.get("value")
        if constant_val is not None:
            if "out" not in output_ports:
                output_ports["out"] = IRPort("out", "out", "data", constant_val)
            else:
                output_ports["out"].value = constant_val
            static_outputs["out"] = constant_val

    return IRNode(
        id=node_id,
        name=name,
        type_name=type_name,
        inputs=input_ports,
        outputs=output_ports,
        is_flow_control=is_flow,
        exec_class=exec_class,
        static_output_values=static_outputs,
    )


def _parse_edge(edge_spec: Dict[str, Any], node_map: Dict[str, IRNode]) -> Optional[IREdge]:
    """Convert a JSON edge dict → IREdge.  Returns None if either endpoint is missing."""
    from_id   = edge_spec["from_node"]
    from_port = edge_spec["from_port"]
    to_id     = edge_spec["to_node"]
    to_port   = edge_spec["to_port"]

    from_node = node_map.get(from_id)
    if not from_node:
        return None

    # Determine edge class from the source output port.
    src_port = from_node.outputs.get(from_port)
    if src_port:
        edge_class = src_port.port_class
    else:
        edge_class = _infer_port_class_from_name(from_port)

    return IREdge(
        from_id=from_id,
        from_port=from_port,
        to_id=to_id,
        to_port=to_port,
        edge_class=edge_class,
    )


# ── Public entry point ────────────────────────────────────────────────────────

def json_to_ir(source: Union[str, Path, Dict[str, Any]]) -> IRGraph:
    """
    Parse a graph JSON description and return an IRGraph.

    Args:
        source: One of:
            - A file path (str or Path) to a JSON file.
            - A pre-parsed dict matching the graph JSON schema.

    Returns:
        An IRGraph ready to pass to ``compiler2.scheduler.Scheduler``.

    Raises:
        FileNotFoundError: If a path is given and the file does not exist.
        KeyError / ValueError: If required fields are missing in the JSON.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = source

    graph_name = data.get("graph_name", "compiled-graph")
    graph_id   = data.get("id", "json-graph")

    node_map: Dict[str, IRNode] = {}
    for node_spec in data.get("nodes", []):
        ir_node = _parse_node(node_spec)
        node_map[ir_node.id] = ir_node

    edges: List[IREdge] = []
    for edge_spec in data.get("edges", []):
        ir_edge = _parse_edge(edge_spec, node_map)
        if ir_edge is not None:
            edges.append(ir_edge)

    return IRGraph(
        id=graph_id,
        name=graph_name,
        nodes=node_map,
        edges=edges,
    )


__all__ = ["json_to_ir", "PORT_SCHEMA"]
