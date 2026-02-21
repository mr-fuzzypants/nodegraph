"""
NodeGraph Compiler v2 — Execution Scheduler
============================================
Maps an IRGraph → IRSchedule: a resolved, ordered execution plan that the
emitter can translate into flat Python source code.

Two scheduling modes:

  LINEAR  — pure data pipeline, no flow-control nodes.
            Produces a flat list of ScheduledNodes in topological order.

  FLOW    — graph contains at least one flow-control driver.
            The driver node is located, then the graph is partitioned into:
              • preamble     — data/constant nodes that feed the driver
              • LoopBlock    — if driver.exec_class == "loop_again"
              • SequenceBlock— if driver.exec_class == "passthrough"

Variable naming
---------------
Every node output port is assigned a Python variable name:

    {safe_node_name}_{port_name}         e.g.  agent_step_type
                                               task_out

where safe_node_name = node.name.lower(), spaces and dashes → underscores.

Input expressions
-----------------
For each input port the scheduler resolves what Python expression to use:
  • Wired port   → variable name of the upstream output port
  • Static value → repr() of the captured default value
  • Absent       → '""'  (empty string as a safe fallback)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .ir import IREdge, IRGraph, IRNode


# ── Scheduled node (resolved reference) ─────────────────────────────────────

@dataclass
class ScheduledNode:
    node_id: str
    node_name: str
    type_name: str

    # port_name → Python variable name for this port's value
    output_vars: Dict[str, str] = field(default_factory=dict)

    # port_name → Python expression for this port's input value
    # (either a variable reference or a literal repr)
    input_exprs: Dict[str, str] = field(default_factory=dict)

    # Raw static output-port values (port_name → value), for templates that
    # need the actual value rather than an expression (e.g. ConstantNode).
    output_port_values: Dict[str, Any] = field(default_factory=dict)


# ── Execution blocks (tree → Python syntax) ──────────────────────────────────

@dataclass
class SequenceBlock:
    """A flat sequence: emits as a; b; c ..."""
    nodes: List[ScheduledNode] = field(default_factory=list)


@dataclass
class LoopBlock:
    """
    A loop driven by a LOOP_AGAIN node (e.g. ToolAgentStreamNode).
    Emits as:
        async for _step in <driver_loop_expr>:
            <body nodes>
        <post nodes>
    """
    driver: ScheduledNode
    body:   List[ScheduledNode] = field(default_factory=list)
    post:   List[ScheduledNode] = field(default_factory=list)


Block = SequenceBlock | LoopBlock


# ── Full execution schedule ───────────────────────────────────────────────────

@dataclass
class IRSchedule:
    graph_name: str
    # Data/constant nodes that must run before the first flow-control node.
    preamble: List[ScheduledNode] = field(default_factory=list)
    # Ordered execution blocks (currently at most one, but extensible).
    blocks:   List[Block]         = field(default_factory=list)


# ── Scheduler ────────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    """Convert a node name to a safe Python identifier prefix."""
    return name.lower().replace(" ", "_").replace("-", "_").replace(".", "_")


class Scheduler:
    def __init__(self, ir: IRGraph):
        self.ir = ir

    # ── Variable naming ───────────────────────────────────────────────────

    def _var(self, node: IRNode, port: str) -> str:
        return f"{_safe_name(node.name)}_{port}"

    # ── Input resolution ──────────────────────────────────────────────────

    def _resolve_input(self, node: IRNode, port_name: str) -> str:
        """
        Determine the Python expression to use for a node's input port.

        Resolution order:
          1. Incoming data edge → reference the upstream output variable.
          2. Static value on the input port → repr().
          3. Fallback → '""'.
        """
        incoming = self.ir.get_incoming(node.id, port_name)
        data_edges = [e for e in incoming if e.edge_class == "data"]

        if data_edges:
            e  = data_edges[0]
            src = self.ir.get_node(e.from_id)
            if src:
                return self._var(src, e.from_port)

        # No wire → use static value from input port
        port = node.inputs.get(port_name)
        if port is not None and port.value is not None:
            return repr(port.value)

        return '""'

    # ── Node scheduling ───────────────────────────────────────────────────

    def _schedule(self, node: IRNode) -> ScheduledNode:
        return ScheduledNode(
            node_id=node.id,
            node_name=node.name,
            type_name=node.type_name,
            output_vars={p: self._var(node, p) for p in node.outputs},
            input_exprs={p: self._resolve_input(node, p) for p in node.inputs},
            output_port_values=dict(node.static_output_values),
        )

    # ── Topological sort of data predecessors ─────────────────────────────

    def _data_preds_topo(self, target_id: str) -> List[IRNode]:
        """
        Topological sort of all non-flow-control ancestors of `target_id`.
        Returns them in execution order (sources first), excluding `target_id`.
        """
        visited: Set[str] = set()
        order: List[IRNode] = []

        def visit(nid: str) -> None:
            if nid in visited:
                return
            visited.add(nid)
            node = self.ir.get_node(nid)
            if node is None:
                return
            # Recurse into data-edge parents first
            for edge in self.ir.get_all_incoming(nid):
                if edge.edge_class == "data":
                    src = self.ir.get_node(edge.from_id)
                    if src and not src.is_flow_control:
                        visit(edge.from_id)
            if not node.is_flow_control and nid != target_id:
                order.append(node)

        visit(target_id)
        return order

    def _topo_all_data(self) -> List[IRNode]:
        """Topological sort of ALL non-flow-control nodes (for pure data pipelines)."""
        visited: Set[str] = set()
        order: List[IRNode] = []

        def visit(nid: str) -> None:
            if nid in visited:
                return
            visited.add(nid)
            for edge in self.ir.edges:
                if edge.to_id == nid and edge.edge_class == "data":
                    visit(edge.from_id)
            node = self.ir.get_node(nid)
            if node and not node.is_flow_control:
                order.append(node)

        for node in self.ir.nodes.values():
            visit(node.id)
        return order

    # ── Control-edge traversal ────────────────────────────────────────────

    def _follow_control(self, from_id: str, port: str) -> List[IRNode]:
        """
        Follow a named control-output edge and collect the downstream chain
        of flow-control nodes (stopping before any that have incoming control
        edges from a DIFFERENT source — i.e. nodes belonging to another branch).
        """
        visited: Set[str] = set()
        chain: List[IRNode] = []

        def follow(nid: str) -> None:
            if nid in visited:
                return
            visited.add(nid)
            node = self.ir.get_node(nid)
            if node is None:
                return
            chain.append(node)
            # Follow onward control edges from this node (e.g. "next")
            for pname, port_ir in node.outputs.items():
                if port_ir.port_class == "control":
                    for edge in self.ir.get_outgoing(nid, pname):
                        tgt = self.ir.get_node(edge.to_id)
                        if tgt and tgt.is_flow_control:
                            follow(edge.to_id)

        for edge in self.ir.get_outgoing(from_id, port):
            follow(edge.to_id)

        return chain

    # ── Driver detection ─────────────────────────────────────────────────

    def _find_driver(self) -> Optional[IRNode]:
        """
        Find the entry flow-control node: the one that has NO incoming
        control edges (i.e. it is initiated by data inputs alone, not by
        another flow-control node).
        """
        nodes_with_incoming_ctrl: Set[str] = {
            e.to_id for e in self.ir.edges if e.edge_class == "control"
        }
        for node in self.ir.nodes.values():
            if node.is_flow_control and node.id not in nodes_with_incoming_ctrl:
                return node
        return None

    # ── Public API ────────────────────────────────────────────────────────

    def build(self, graph_name: str = "graph") -> IRSchedule:
        """Build an IRSchedule from the IRGraph."""

        driver = self._find_driver()

        # ── Pure data pipeline ────────────────────────────────────────────
        if driver is None:
            data_nodes = self._topo_all_data()
            return IRSchedule(
                graph_name=graph_name,
                preamble=[self._schedule(n) for n in data_nodes],
                blocks=[],
            )

        # ── Flow-control graph ────────────────────────────────────────────
        preamble_nodes   = self._data_preds_topo(driver.id)
        driver_scheduled = self._schedule(driver)

        if driver.exec_class == "loop_again":
            body_nodes = self._follow_control(driver.id, "loop_body")
            post_nodes = self._follow_control(driver.id, "completed")
            block: Block = LoopBlock(
                driver=driver_scheduled,
                body=[self._schedule(n) for n in body_nodes],
                post=[self._schedule(n) for n in post_nodes],
            )

        elif driver.exec_class == "branch":
            # Branch support is structural scaffolding; template filling
            # requires a BranchNodeTemplate (see templates.py).
            true_nodes  = self._follow_control(driver.id, "true_out")
            false_nodes = self._follow_control(driver.id, "false_out")
            block = SequenceBlock(
                nodes=[driver_scheduled]
                      + [self._schedule(n) for n in true_nodes]
                      + [self._schedule(n) for n in false_nodes],
            )

        else:
            # passthrough: linear sequence starting at driver
            # Follow the first control output (usually "next")
            ctrl_out_ports = [
                p for p, ir_p in driver.outputs.items()
                if ir_p.port_class == "control"
            ]
            chain_nodes: List[IRNode] = []
            if ctrl_out_ports:
                chain_nodes = self._follow_control(driver.id, ctrl_out_ports[0])

            block = SequenceBlock(
                nodes=[driver_scheduled] + [self._schedule(n) for n in chain_nodes],
            )

        return IRSchedule(
            graph_name=graph_name,
            preamble=[self._schedule(n) for n in preamble_nodes],
            blocks=[block],
        )
