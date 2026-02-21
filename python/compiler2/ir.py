"""
NodeGraph Compiler v2 — Intermediate Representation
====================================================
IRGraph is a decoupled structural snapshot of a live Graph object.

It serves as the stable data model shared between all pipeline phases:

    Graph  →  [extractor]  →  IRGraph
                                  ↓
                           [scheduler]  →  IRSchedule
                                              ↓
                                         [emitter]  →  Python source str

Design goals:
  - No runtime dependencies on the nodegraph execution engine.
  - Serialisable (dataclasses only, no live node references).
  - Language-agnostic: the same IRGraph could target Python, JS, or Rust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Port ─────────────────────────────────────────────────────────────────────

@dataclass
class IRPort:
    name: str
    direction: str     # "in" | "out"
    port_class: str    # "data" | "control"
    value: Any = None  # static default value (may be None for wired ports)


# ── Node ─────────────────────────────────────────────────────────────────────

@dataclass
class IRNode:
    id: str
    name: str
    type_name: str

    inputs: Dict[str, IRPort]   = field(default_factory=dict)
    outputs: Dict[str, IRPort]  = field(default_factory=dict)
    is_flow_control: bool       = False

    # Execution class — inferred by extractor from port structure:
    #   "constant"    no inputs, pure value source
    #   "data"        standard data-push node (CONTINUE)
    #   "loop_again"  flow-control node that loops (has loop_body + completed ports)
    #   "branch"      flow-control node with conditions (true_out + false_out)
    #   "passthrough" flow-control node that simply forwards control (exec → next)
    exec_class: str = "data"

    # Static values captured from output ports at extraction time.
    # ConstantNode stores its value here (outputs["out"].value).
    static_output_values: Dict[str, Any] = field(default_factory=dict)


# ── Edge ─────────────────────────────────────────────────────────────────────

@dataclass
class IREdge:
    from_id: str
    from_port: str
    to_id: str
    to_port: str
    edge_class: str = "data"   # "data" | "control"


# ── Graph ─────────────────────────────────────────────────────────────────────

@dataclass
class IRGraph:
    id: str
    name: str
    nodes: Dict[str, IRNode]  = field(default_factory=dict)
    edges: List[IREdge]       = field(default_factory=list)

    # ── Convenience queries ────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[IRNode]:
        return self.nodes.get(node_id)

    def get_node_by_name(self, name: str) -> Optional[IRNode]:
        return next((n for n in self.nodes.values() if n.name == name), None)

    def get_outgoing(self, node_id: str, port: str) -> List[IREdge]:
        return [e for e in self.edges
                if e.from_id == node_id and e.from_port == port]

    def get_incoming(self, node_id: str, port: str) -> List[IREdge]:
        return [e for e in self.edges
                if e.to_id == node_id and e.to_port == port]

    def get_all_incoming(self, node_id: str) -> List[IREdge]:
        return [e for e in self.edges if e.to_id == node_id]

    def get_all_outgoing(self, node_id: str) -> List[IREdge]:
        return [e for e in self.edges if e.from_id == node_id]
