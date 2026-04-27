"""
NodeGraph Compiler v2 — Graph Extractor
========================================
Converts a live nodegraph.python.core.GraphPrimitives.Graph object
into a self-contained IRGraph.

Deliberately avoids importing node implementation modules — all
inference is purely structural (port names, port types, class names).
This keeps the compiler decoupled from the execution engine.

Exec-class inference heuristic (no node class imports required):
  ┌──────────────┬─────────────────────────────────────────────────┐
  │ exec_class   │ Structural signal                               │
  ├──────────────┼─────────────────────────────────────────────────┤
  │ constant     │ is_flow_control=False AND no data input edges   │
  │ data         │ is_flow_control=False                           │
  │ loop_again   │ is_flow_control=True, has "loop_body"+"completed│
  │ branch       │ is_flow_control=True, has "true_out"+"false_out"│
  │ passthrough  │ is_flow_control=True, all others                │
  └──────────────┴─────────────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .ir import IREdge, IRGraph, IRNode, IRPort

if TYPE_CHECKING:
    from nodegraph.python.core.GraphPrimitives import Graph


# ── Port class detection (no Types import needed) ────────────────────────────

def _is_control_port(port) -> bool:
    """Determine if a port is a control port by inspecting its class name."""
    return "Control" in type(port).__name__


def _extract_port(port, direction: str) -> IRPort:
    port_class = "control" if _is_control_port(port) else "data"
    return IRPort(
        name=port.port_name,
        direction=direction,
        port_class=port_class,
        value=getattr(port, "value", None),
    )


# ── Exec-class inference ─────────────────────────────────────────────────────

def _infer_exec_class(node, graph_edges) -> str:
    is_flow = getattr(node, "is_flow_control_node", False)
    out_names = set(node.outputs.keys())
    in_names  = set(node.inputs.keys())

    if not is_flow:
        # Check if this node has any incoming data edges
        has_data_inputs = any(
            e.to_node_id == node.id
            and not _is_control_port(node.inputs.get(e.to_port_name, _DummyPort()))
            for e in graph_edges
        )
        # Also check if node has any data input ports at all
        has_data_input_ports = any(
            not _is_control_port(p) for p in node.inputs.values()
        )
        if not has_data_input_ports:
            return "constant"
        return "data"

    if "loop_body" in out_names and "completed" in out_names:
        return "loop_again"

    if "true_out" in out_names and "false_out" in out_names:
        return "branch"

    return "passthrough"


class _DummyPort:
    """Sentinel used when a port lookup fails during exec-class inference."""
    pass


# ── Public entry point ───────────────────────────────────────────────────────

def extract(graph: "Graph", graph_name: str = "graph") -> IRGraph:
    """
    Extract an IRGraph from a live Graph object.

    Args:
        graph:      The live nodegraph Graph to compile.
        graph_name: Human-readable name for the compiled graph.

    Returns:
        A fully populated IRGraph (no live references, safe to serialise).
    """
    node_map: dict[str, IRNode] = {}

    for node_id, node in graph.nodes.items():
        # Skip the NodeNetwork container node itself — it is the graph host,
        # not a computation node.  Detected via isNetwork() or by the fact
        # that its id matches the network_id of child nodes.
        if getattr(node, "isNetwork", lambda: False)():
            continue

        inputs  = {k: _extract_port(p, "in")  for k, p in node.inputs.items()}
        outputs = {k: _extract_port(p, "out") for k, p in node.outputs.items()}

        exec_class = _infer_exec_class(node, graph.edges)

        # For ConstantNode (and similar), the meaningful "value" lives on the
        # OUTPUT port, not an input port.  Capture it so the emitter can read
        # it without inspecting live objects.
        static_output_values = {
            k: p.value
            for k, p in node.outputs.items()
            if not _is_control_port(p) and p.value is not None
        }

        node_map[node_id] = IRNode(
            id=node_id,
            name=node.name,
            type_name=getattr(node, "type", type(node).__name__),
            inputs=inputs,
            outputs=outputs,
            is_flow_control=getattr(node, "is_flow_control_node", False),
            exec_class=exec_class,
            static_output_values=static_output_values,
        )

    edges: list[IREdge] = []
    for edge in graph.edges:
        # Skip edges that reference the network container node
        if edge.from_node_id not in node_map or edge.to_node_id not in node_map:
            continue

        # Determine edge class from the SOURCE output port type.
        src_node = graph.nodes.get(edge.from_node_id)
        edge_class = "data"
        if src_node:
            src_port = src_node.outputs.get(edge.from_port_name)
            if src_port and _is_control_port(src_port):
                edge_class = "control"

        edges.append(IREdge(
            from_id=edge.from_node_id,
            from_port=edge.from_port_name,
            to_id=edge.to_node_id,
            to_port=edge.to_port_name,
            edge_class=edge_class,
        ))

    # Use the network_id shared by all nodes as the IRGraph id.
    graph_id = next(
        (n.network_id for n in graph.nodes.values() if getattr(n, "network_id", None)),
        "unknown",
    )

    return IRGraph(
        id=graph_id,
        name=graph_name,
        nodes=node_map,
        edges=edges,
    )
