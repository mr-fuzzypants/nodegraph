"""
Graph serializer — Python port of server/src/serializers/graphSerializer.ts.

Converts Python NodeNetwork / Node / NodePort objects into JSON-safe dicts
that match the SerializedNetwork wire shape the React UI expects.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from typing import Any, Dict, List, Optional, Set, Tuple

from nodegraph.python.core.Types import NodeKind, PortDirection, PortFunction

# ── Wire shapes (dicts, not TypedDicts, for easy JSON serialisation) ──────────
# These mirror the TypeScript interfaces in graphSerializer.ts.

# SerializedPort keys: name, function, direction, valueType, value, connected
# SerializedNode keys: id, name, type, kind, isFlowControlNode, path, inputs,
#                      outputs, subnetworkId, position
# SerializedEdge keys: id, sourceNodeId, sourcePortName, targetNodeId,
#                      targetPortName
# SerializedNetwork keys: id, name, path, parentId, nodes, edges


# ── Helpers ───────────────────────────────────────────────────────────────────

def _value_type_str(port: Any) -> str:
    """Return the uppercase string representation of a port's data_type."""
    dt = getattr(port, "data_type", None)
    if dt is None:
        return "ANY"
    val = getattr(dt, "value", None)
    if val is None:
        return "ANY"
    return str(val).upper()


def _serialize_port(port: Any, connected: bool = False) -> Dict[str, Any]:
    fn = getattr(port, "function", None)
    direction = getattr(port, "direction", None)
    return {
        "name": getattr(port, "port_name", ""),
        "function": "DATA" if fn == PortFunction.DATA else "CONTROL",
        "direction": "OUTPUT" if direction == PortDirection.OUTPUT else "INPUT",
        "valueType": _value_type_str(port),
        "value": getattr(port, "value", None),
        "connected": connected,
    }


def _serialize_node(
    node: Any,
    positions: Dict[str, Dict[str, float]],
    connected_inputs: Set[str],
    graph: Any,
) -> Dict[str, Any]:
    is_net = getattr(node, "kind", NodeKind.FUNCTION) == NodeKind.NETWORK

    try:
        path = graph.get_path(node.id)
    except Exception:
        path = getattr(node, "name", node.id)

    inputs_dict: Dict[str, Any] = getattr(node, "inputs", {})
    outputs_dict: Dict[str, Any] = getattr(node, "outputs", {})

    return {
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "kind": "NETWORK" if is_net else "FUNCTION",
        "isFlowControlNode": getattr(node, "is_flow_control_node", False),
        "path": path,
        "inputs": [
            _serialize_port(p, f"{node.id}:{getattr(p, 'port_name', '')}" in connected_inputs)
            for p in inputs_dict.values()
        ],
        "outputs": [
            _serialize_port(p, False)
            for p in outputs_dict.values()
        ],
        "subnetworkId": node.id if is_net else None,
        "position": positions.get(node.id, {"x": 0, "y": 0}),
    }


def _serialize_self_node(
    network: Any,
    positions: Dict[str, Dict[str, float]],
    graph: Any,
) -> Dict[str, Any]:
    """
    When viewing INSIDE a NodeNetwork, the network node itself acts as a
    bidirectional tunnel proxy — mirroring serializeNetworkSelfNode in TS.

    - network.inputs  (tunnel inputs)  → emitted as OUTPUT-direction handles
      so internal nodes can connect FROM them.
    - network.outputs (tunnel outputs) → emitted as INPUT-direction handles
      so internal nodes can connect TO them.
    """
    inputs_dict: Dict[str, Any] = getattr(network, "inputs", {})
    outputs_dict: Dict[str, Any] = getattr(network, "outputs", {})

    try:
        path = graph.get_path(network.id)
    except Exception:
        path = getattr(network, "name", network.id)

    # Tunnel inputs → OUTPUT-direction port dicts
    tunnel_outputs = []
    for port in inputs_dict.values():
        fn = getattr(port, "function", None)
        tunnel_outputs.append(
            {
                "name": getattr(port, "port_name", ""),
                "function": "CONTROL" if fn == PortFunction.CONTROL else "DATA",
                "direction": "OUTPUT",
                "valueType": _value_type_str(port),
                "value": getattr(port, "value", None),
                "connected": False,
            }
        )

    # Tunnel outputs → INPUT-direction port dicts
    tunnel_inputs = []
    for port in outputs_dict.values():
        fn = getattr(port, "function", None)
        tunnel_inputs.append(
            {
                "name": getattr(port, "port_name", ""),
                "function": "CONTROL" if fn == PortFunction.CONTROL else "DATA",
                "direction": "INPUT",
                "valueType": _value_type_str(port),
                "value": getattr(port, "value", None),
                "connected": False,
            }
        )

    return {
        "id": network.id,
        "name": network.name,
        "type": "SELF",
        "kind": "SELF",
        "isFlowControlNode": False,
        "path": path,
        "inputs": tunnel_inputs,
        "outputs": tunnel_outputs,
        "subnetworkId": None,
        "position": positions.get(f"{network.id}:self", {"x": -300, "y": 140}),
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def serialize_network(
    network: Any,
    positions: Dict[str, Dict[str, float]],
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Serialize *network* into a SerializedNetwork dict.

    :param network:   A Python NodeNetwork instance.
    :param positions: Dict mapping node_id (or "<node_id>:self") → {x, y}.
    :param parent_id: Id of the parent network, or None for root.
    """
    graph = network.graph
    nodes: List[Dict[str, Any]] = []

    # Build set of all input ports that have an incoming edge so we can mark
    # them "connected" in the port serialization.
    connected_inputs: Set[str] = set()
    for edge in graph.edges:
        connected_inputs.add(f"{edge.to_node_id}:{edge.to_port_name}")

    # Collect the IDs of nodes that belong to this network layer, plus the
    # network node itself (for tunnel edges).
    node_id_set: Set[str] = set()

    for node_id, node in graph.nodes.items():
        if node is None:
            continue
        if getattr(node, "network_id", None) != network.id:
            continue
        nodes.append(_serialize_node(node, positions, connected_inputs, graph))
        node_id_set.add(node_id)

    # The network node itself is a valid edge endpoint for tunnel connections.
    node_id_set.add(network.id)

    # Emit the SELF proxy node if this network has any tunnel ports.
    inputs_dict = getattr(network, "inputs", {})
    outputs_dict = getattr(network, "outputs", {})
    if inputs_dict or outputs_dict:
        nodes.insert(0, _serialize_self_node(network, positions, graph))

    # Only include edges whose both endpoints belong to this network scope.
    edges: List[Dict[str, Any]] = [
        {
            "id": f"{e.from_node_id}:{e.from_port_name}\u2192{e.to_node_id}:{e.to_port_name}",
            "sourceNodeId": e.from_node_id,
            "sourcePortName": e.from_port_name,
            "targetNodeId": e.to_node_id,
            "targetPortName": e.to_port_name,
        }
        for e in graph.edges
        if e.from_node_id in node_id_set and e.to_node_id in node_id_set
    ]

    try:
        net_path = graph.get_path(network.id)
    except Exception:
        net_path = f"/{network.name}"

    return {
        "id": network.id,
        "name": network.name,
        "path": net_path,
        "parentId": parent_id,
        "nodes": nodes,
        "edges": edges,
    }
