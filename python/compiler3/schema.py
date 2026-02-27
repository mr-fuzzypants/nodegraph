"""
NodeGraph Compiler v3 — Graph JSON Schema + Validator
=======================================================
Defines the canonical serialisation format for NodeGraph graphs and provides
a lightweight validator that runs without any third-party JSON Schema library.

Canonical JSON format
---------------------

    {
      "graph_name": "streaming-agent-simple",   // human label (str, required)
      "id":         "optional-stable-uuid",      // stable graph ID (str, optional)
      "nodes": [
        {
          "id":      "node_001",                 // unique within this graph (str, required)
          "type":    "ConstantNode",             // registered type name (str, required)
          "name":    "Task",                     // display name (str, optional → defaults to id)
          "inputs":  { "value": "Hello" },      // static port values (dict, optional)
          "outputs": {}                          // rarely used; reserved (dict, optional)
        }
      ],
      "edges": [
        {
          "from_node": "node_001",              // source node id (str, required)
          "from_port": "out",                   // source port name (str, required)
          "to_node":   "node_002",              // target node id (str, required)
          "to_port":   "task"                   // target port name (str, required)
        }
      ]
    }

Known node types (as of compiler v3)
-------------------------------------
  ConstantNode        ─ data source, no inputs, output: out
  AddNode             ─ data: inputs a, b → output sum
  MultiplyNode        ─ data: inputs a, b → output product
  PrintNode           ─ flow: exec → (prints value) → next
  BranchNode          ─ flow: exec + condition → true_out / false_out
  ForLoopNode         ─ loop: exec + start/end → loop_body / completed / index
  AccumulatorNode     ─ flow: exec + val → next
  StepPrinterNode     ─ flow: exec + step_type/step_content/tool_name → next
  ToolAgentNode       ─ data: task + tools + model → result/tool_calls/steps
  ToolAgentStreamNode ─ loop: exec + task + tools + model →
                               loop_body/completed + step_type/step_content/tool_name/result
  LLMNode             ─ data: prompt + system_prompt + model + temperature → response
  PromptTemplateNode  ─ data: template + variables → prompt
  VectorNode          ─ data: x/y/z → vec
  DotProductNode      ─ data: vec_a + vec_b → result
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


# ── Known types ───────────────────────────────────────────────────────────────

KNOWN_NODE_TYPES: frozenset[str] = frozenset({
    "ConstantNode",
    "AddNode",
    "MultiplyNode",
    "PrintNode",
    "BranchNode",
    "ForLoopNode",
    "ForEachNode",
    "AccumulatorNode",
    "StepPrinterNode",
    "ToolAgentNode",
    "ToolAgentStreamNode",
    "LLMNode",
    "PromptTemplateNode",
    "VectorNode",
    "DotProductNode",
})


# ── Validation helpers ────────────────────────────────────────────────────────

class SchemaError(ValueError):
    """Raised when graph JSON fails structural validation."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SchemaError(message)


def _require_keys(obj: Dict, keys: List[str], context: str) -> None:
    for key in keys:
        _require(key in obj, f"{context}: missing required field '{key}'")


# ── Public validator ─────────────────────────────────────────────────────────

def validate(data: Dict[str, Any], *, strict: bool = False) -> None:
    """
    Validate a parsed graph JSON dict.

    Args:
        data:   A pre-parsed dict (result of json.load / json.loads).
        strict: When True, raise SchemaError for unknown node types.
                When False (default), unknown types produce a warning.

    Raises:
        SchemaError: On any structural violation.
    """
    _require(isinstance(data, dict), "graph JSON must be a JSON object at the top level")
    _require_keys(data, ["graph_name", "nodes", "edges"], "graph root")

    _require(isinstance(data["graph_name"], str), "graph_name must be a string")
    _require(isinstance(data["nodes"],     list), "nodes must be a list")
    _require(isinstance(data["edges"],     list), "edges must be a list")

    # ── Validate nodes ──────────────────────────────────────────────────────

    node_ids: set[str] = set()

    for i, node in enumerate(data["nodes"]):
        ctx = f"nodes[{i}]"
        _require(isinstance(node, dict), f"{ctx}: each node must be a JSON object")
        _require_keys(node, ["id", "type"], ctx)
        _require(isinstance(node["id"],   str), f"{ctx}.id must be a string")
        _require(isinstance(node["type"], str), f"{ctx}.type must be a string")
        _require(
            node["id"] not in node_ids,
            f"{ctx}: duplicate node id '{node['id']}'",
        )
        node_ids.add(node["id"])

        if "inputs" in node:
            _require(isinstance(node["inputs"], dict), f"{ctx}.inputs must be an object")
        if "outputs" in node:
            _require(isinstance(node["outputs"], dict), f"{ctx}.outputs must be an object")

        type_name = node["type"]
        if type_name not in KNOWN_NODE_TYPES:
            msg = f"{ctx}: unknown node type '{type_name}'"
            if strict:
                raise SchemaError(msg)
            else:
                import warnings
                warnings.warn(msg + " (compilation may produce a TODO stub)", stacklevel=3)

    # ── Validate edges ──────────────────────────────────────────────────────

    for i, edge in enumerate(data["edges"]):
        ctx = f"edges[{i}]"
        _require(isinstance(edge, dict), f"{ctx}: each edge must be a JSON object")
        _require_keys(edge, ["from_node", "from_port", "to_node", "to_port"], ctx)

        for field in ("from_node", "from_port", "to_node", "to_port"):
            _require(isinstance(edge[field], str), f"{ctx}.{field} must be a string")

        _require(
            edge["from_node"] in node_ids,
            f"{ctx}: from_node '{edge['from_node']}' not found in nodes",
        )
        _require(
            edge["to_node"] in node_ids,
            f"{ctx}: to_node '{edge['to_node']}' not found in nodes",
        )


def validate_file(path: Union[str, Path], *, strict: bool = False) -> Dict[str, Any]:
    """
    Load and validate a graph JSON file.

    Returns:
        The parsed dict on success.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        SchemaError: If the graph structure is invalid.
    """
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    validate(data, strict=strict)
    return data


__all__ = ["KNOWN_NODE_TYPES", "SchemaError", "validate", "validate_file"]
