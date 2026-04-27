"""
Graph REST routes — Python port of server/src/routes/graphRoutes.ts.

All routes are mounted under /api by main.py.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nodegraph.python.core.WorkflowManager import WorkflowManager
from nodegraph.python.server.serializers.graph_serializer import serialize_network
from nodegraph.python.server.state import graph_state
from nodegraph.python.server.trace.trace_emitter import global_tracer

router = APIRouter()


# ── POST /step/resume ─────────────────────────────────────────────────────────

@router.post("/step/resume")
async def step_resume() -> Dict[str, Any]:
    print("[step] POST /step/resume — calling resume()")
    global_tracer.resume()
    return {"ok": True}

# ── POST /executions/:runId/nodes/:nodeId/human-input ────────────────────────
# Delivers a human response to a waiting HumanInputNode.
# Stateless: looks up the node directly from the active executor — no global
# registry required.
#
#   curl -X POST http://localhost:3001/api/executions/<run_id>/nodes/<node_id>/human-input \
#        -H 'Content-Type: application/json' \
#        -d '{"response": "Alice"}'

class HumanInputBody(BaseModel):
    response: str

@router.post("/executions/{run_id}/nodes/{node_id}/human-input")
async def provide_human_input(run_id: str, node_id: str, body: HumanInputBody) -> Dict[str, Any]:
    executor = graph_state.active_executors.get(run_id)
    if executor is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active execution with runId '{run_id}'",
        )
    node = executor.graph.get_node_by_id(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    # Check _waiting flag: set to True inside compute() BEFORE HUMAN_INPUT_REQUIRED
    # fires, and only cleared after compute() unblocks.  executor.waiting_nodes is
    # populated AFTER compute() returns so it will always be empty here.
    if not getattr(node, "_waiting", False):
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' is not currently waiting for human input",
        )
    # Unblock the asyncio.Event that HumanInputNode.compute() is waiting on.
    # Both coroutines share the same event loop so this wakes immediately.
    node.provide_response(body.response)
    print(f"[human-input] run={run_id} node={node_id} response={body.response!r}", flush=True)
    return {"ok": True, "runId": run_id, "nodeId": node_id}

# ── GET /networks/root ────────────────────────────────────────────────────────

@router.get("/networks/root")
async def get_root_network() -> Dict[str, Any]:
    net = graph_state.root_network
    return {"id": net.id, "name": net.name}


# ── GET /networks ─────────────────────────────────────────────────────────────

@router.get("/networks")
async def list_networks() -> List[Dict[str, Any]]:
    result = []
    for net in graph_state.all_networks.values():
        try:
            path = net.graph.get_path(net.id)
        except Exception:
            path = f"/{net.name}"
        result.append(
            {
                "id": net.id,
                "name": net.name,
                "path": path,
                "parentId": getattr(net, "network_id", None),
            }
        )
    return result


# ── GET /networks/:id ─────────────────────────────────────────────────────────

@router.get("/networks/{network_id}")
async def get_network(network_id: str) -> Dict[str, Any]:
    network = graph_state.get_network(network_id)
    if network is None:
        raise HTTPException(status_code=404, detail="Network not found")
    parent_id = getattr(network, "network_id", None)
    return serialize_network(network, graph_state.positions, parent_id)


# ── POST /networks ────────────────────────────────────────────────────────────

class CreateNetworkBody(BaseModel):
    name: str


@router.post("/networks", status_code=201)
async def create_network(body: CreateNetworkBody) -> Dict[str, Any]:
    try:
        net = graph_state.create_subnetwork(graph_state.root_network.id, body.name)
        return {"id": net.id, "name": net.name}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── POST /networks/:id/networks ───────────────────────────────────────────────

@router.post("/networks/{network_id}/networks", status_code=201)
async def create_subnetwork(network_id: str, body: CreateNetworkBody) -> Dict[str, Any]:
    try:
        subnet = graph_state.create_subnetwork(network_id, body.name)
        return {"id": subnet.id, "name": subnet.name}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── POST /networks/:id/nodes ──────────────────────────────────────────────────

class CreateNodeBody(BaseModel):
    type: str
    name: str
    position: Optional[Dict[str, float]] = None


@router.post("/networks/{network_id}/nodes", status_code=201)
async def create_node(network_id: str, body: CreateNodeBody) -> Dict[str, Any]:
    try:
        node = graph_state.create_node(network_id, body.type, body.name)
        if body.position:
            graph_state.set_position(node.id, body.position["x"], body.position["y"])
        return {"id": node.id, "name": node.name, "type": node.type}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── DELETE /networks/:id/nodes/:nodeId ────────────────────────────────────────

@router.delete("/networks/{network_id}/nodes/{node_id}", status_code=204)
async def delete_node(network_id: str, node_id: str) -> Response:
    try:
        graph_state.delete_node(network_id, node_id)
        return Response(status_code=204)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── POST /networks/:id/group-nodes ───────────────────────────────────────────

class GroupNodesBody(BaseModel):
    nodeIds: List[str]
    name: str = ""


@router.post("/networks/{network_id}/group-nodes", status_code=201)
async def group_nodes(network_id: str, body: GroupNodesBody) -> Dict[str, Any]:
    try:
        subnet_id = graph_state.group_nodes(network_id, body.nodeIds, body.name)
        network = graph_state.get_network(network_id)
        if network is None:
            raise HTTPException(status_code=404, detail="Network not found")
        return serialize_network(network, graph_state.positions, getattr(network, "network_id", None))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── POST /networks/:id/edges ──────────────────────────────────────────────────

class EdgeBody(BaseModel):
    sourceNodeId: str
    sourcePort: str
    targetNodeId: str
    targetPort: str


@router.post("/networks/{network_id}/edges", status_code=201)
async def add_edge(network_id: str, body: EdgeBody) -> Dict[str, Any]:
    try:
        graph_state.add_edge(
            network_id,
            body.sourceNodeId,
            body.sourcePort,
            body.targetNodeId,
            body.targetPort,
        )
        network = graph_state.get_network(network_id)
        return serialize_network(network, graph_state.positions, getattr(network, "network_id", None))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── DELETE /networks/:id/edges ────────────────────────────────────────────────
# FastAPI does not natively support DELETE with a JSON body, so we parse it via
# the request object directly.

@router.delete("/networks/{network_id}/edges", status_code=204)
async def delete_edge(network_id: str, body: EdgeBody) -> Response:
    try:
        graph_state.remove_edge(
            network_id,
            body.sourceNodeId,
            body.sourcePort,
            body.targetNodeId,
            body.targetPort,
        )
        return Response(status_code=204)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── PUT /networks/:id/nodes/:nodeId/position ──────────────────────────────────

class PositionBody(BaseModel):
    x: float
    y: float


@router.put("/networks/{network_id}/nodes/{node_id}/position", status_code=204)
async def set_node_position(
    network_id: str, node_id: str, body: PositionBody
) -> Response:
    graph_state.set_position(node_id, body.x, body.y)
    return Response(status_code=204)


class RenameNodeBody(BaseModel):
    name: str


@router.put("/networks/{network_id}/nodes/{node_id}/name", status_code=204)
async def rename_node(
    network_id: str, node_id: str, body: RenameNodeBody
) -> Response:
    try:
        graph_state.rename_node(network_id, node_id, body.name)
        return Response(status_code=204)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── PUT /networks/:id/nodes/:nodeId/ports/:portName ───────────────────────────

class SetPortValueBody(BaseModel):
    value: Any


@router.put(
    "/networks/{network_id}/nodes/{node_id}/ports/{port_name}", status_code=204
)
async def set_port_value(
    network_id: str, node_id: str, port_name: str, body: SetPortValueBody
) -> Response:
    try:
        graph_state.set_port_value(network_id, node_id, port_name, body.value)
        return Response(status_code=204)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── POST /networks/:id/tunnel-ports ──────────────────────────────────────────

class TunnelPortBody(BaseModel):
    name: str
    direction: str  # 'input' | 'output'
    function: str = "DATA"
    valueType: str = "ANY"


class TunnelInputConnectionBody(BaseModel):
    sourceNodeId: Optional[str] = None
    sourcePort: Optional[str] = None
    targetNodeId: Optional[str] = None
    targetPort: Optional[str] = None


class TunnelOutputConnectionBody(BaseModel):
    sourceNodeId: str
    sourcePort: str


@router.post("/networks/{network_id}/tunnel-ports", status_code=201)
async def add_tunnel_port(network_id: str, body: TunnelPortBody) -> Dict[str, Any]:
    try:
        if not body.name or not body.name.strip():
            raise HTTPException(status_code=400, detail="`name` required")
        if body.direction not in ("input", "output"):
            raise HTTPException(
                status_code=400,
                detail='`direction` must be "input" or "output"',
            )
        graph_state.add_tunnel_port(
            network_id,
            body.name.strip(),
            body.direction,
            body.function,
            body.valueType,
        )
        network = graph_state.get_network(network_id)
        return serialize_network(network, graph_state.positions, getattr(network, "network_id", None))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/networks/{network_id}/tunnel-input-connections", status_code=201)
async def connect_to_new_tunnel_input(
    network_id: str,
    body: TunnelInputConnectionBody,
) -> Dict[str, Any]:
    try:
        if body.sourceNodeId is not None or body.sourcePort is not None:
            source_node_id = (body.sourceNodeId or "").strip()
            source_port = (body.sourcePort or "").strip()
            if not source_node_id:
                raise HTTPException(status_code=400, detail="`sourceNodeId` required")
            if not source_port:
                raise HTTPException(status_code=400, detail="`sourcePort` required")

            graph_state.connect_to_new_tunnel_input(
                network_id,
                source_node_id,
                source_port,
            )
        elif body.targetNodeId is not None or body.targetPort is not None:
            target_node_id = (body.targetNodeId or "").strip()
            target_port = (body.targetPort or "").strip()
            if not target_node_id:
                raise HTTPException(status_code=400, detail="`targetNodeId` required")
            if not target_port:
                raise HTTPException(status_code=400, detail="`targetPort` required")

            graph_state.connect_new_tunnel_input_to_target(
                network_id,
                target_node_id,
                target_port,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide either sourceNodeId/sourcePort or targetNodeId/targetPort",
            )
        network = graph_state.get_network(network_id)
        return serialize_network(
            network,
            graph_state.positions,
            getattr(network, "network_id", None),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/networks/{network_id}/tunnel-output-connections", status_code=201)
async def connect_to_new_tunnel_output(
    network_id: str,
    body: TunnelOutputConnectionBody,
) -> Dict[str, Any]:
    try:
        source_node_id = body.sourceNodeId.strip()
        source_port = body.sourcePort.strip()
        if not source_node_id:
            raise HTTPException(status_code=400, detail="`sourceNodeId` required")
        if not source_port:
            raise HTTPException(status_code=400, detail="`sourcePort` required")

        graph_state.connect_source_to_new_tunnel_output(
            network_id,
            source_node_id,
            source_port,
        )
        network = graph_state.get_network(network_id)
        return serialize_network(
            network,
            graph_state.positions,
            getattr(network, "network_id", None),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class DynamicInputPortBody(BaseModel):
    name: str
    valueType: str


class DynamicOutputPortBody(BaseModel):
    name: str
    function: str = "DATA"
    valueType: str = "any"


@router.post("/networks/{network_id}/nodes/{node_id}/input-ports", status_code=201)
async def add_dynamic_input_port(
    network_id: str, node_id: str, body: DynamicInputPortBody
) -> Dict[str, Any]:
    try:
        if not body.name or not body.name.strip():
            raise HTTPException(status_code=400, detail="`name` required")
        graph_state.add_dynamic_input_port(
            network_id,
            node_id,
            body.name.strip(),
            body.valueType,
        )
        network = graph_state.get_network(network_id)
        return serialize_network(network, graph_state.positions, getattr(network, "network_id", None))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/networks/{network_id}/nodes/{node_id}/input-ports/{port_name}", status_code=204)
async def delete_dynamic_input_port(
    network_id: str,
    node_id: str,
    port_name: str,
) -> Response:
    try:
        graph_state.remove_dynamic_input_port(network_id, node_id, port_name)
        return Response(status_code=204)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/networks/{network_id}/nodes/{node_id}/output-ports", status_code=201)
async def add_dynamic_output_port(
    network_id: str, node_id: str, body: DynamicOutputPortBody
) -> Dict[str, Any]:
    try:
        if not body.name or not body.name.strip():
            raise HTTPException(status_code=400, detail="`name` required")
        graph_state.add_dynamic_output_port(
            network_id,
            node_id,
            body.name.strip(),
            body.valueType,
            body.function,
        )
        network = graph_state.get_network(network_id)
        return serialize_network(network, graph_state.positions, getattr(network, "network_id", None))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/networks/{network_id}/nodes/{node_id}/output-ports/{port_name}", status_code=204)
async def delete_dynamic_output_port(
    network_id: str,
    node_id: str,
    port_name: str,
) -> Response:
    try:
        graph_state.remove_dynamic_output_port(network_id, node_id, port_name)
        return Response(status_code=204)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── DELETE /networks/:id/tunnel-ports/:portName ───────────────────────────────

@router.delete("/networks/{network_id}/tunnel-ports/{port_name}", status_code=204)
async def delete_tunnel_port(
    network_id: str,
    port_name: str,
    direction: str = Query(..., description='"input" or "output"'),
) -> Response:
    try:
        if direction not in ("input", "output"):
            raise HTTPException(
                status_code=400,
                detail='`direction` query param must be "input" or "output"',
            )
        graph_state.remove_tunnel_port(network_id, port_name, direction)
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── PUT /networks/:id/tunnel-ports/:portName ──────────────────────────────────

class RenameTunnelPortBody(BaseModel):
    newName: str
    direction: str  # 'input' | 'output'


@router.put("/networks/{network_id}/tunnel-ports/{port_name}", status_code=204)
async def rename_tunnel_port(
    network_id: str, port_name: str, body: RenameTunnelPortBody
) -> Response:
    try:
        new_name = body.newName.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="`newName` required")
        if body.direction not in ("input", "output"):
            raise HTTPException(
                status_code=400,
                detail='`direction` must be "input" or "output"',
            )
        graph_state.rename_tunnel_port(network_id, port_name, new_name, body.direction)
        return Response(status_code=204)
    except HTTPException:
        raise
    except ValueError as exc:
        # Duplicate name or not-found → 409 Conflict / 400 Bad Request
        msg = str(exc)
        status = 409 if "already exists" in msg else 400
        raise HTTPException(status_code=status, detail=msg)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── GET /node-types ───────────────────────────────────────────────────────────

@router.get("/node-types")
async def get_node_types() -> List[str]:
    from nodegraph.python.core.Node import Node

    return list(Node._node_registry.keys()) if Node._node_registry else []


@router.get("/port-types")
async def get_port_types() -> List[str]:
    from nodegraph.python.core.Types import ValueType

    return [value_type.name for value_type in ValueType]


# ── POST /networks/:id/execute/:nodeId ───────────────────────────────────────

@router.post("/networks/{network_id}/execute/{node_id}")
async def execute_node(
    network_id: str,
    node_id: str,
    step: bool = Query(False, description="Enable step-through mode"),
) -> Dict[str, Any]:
    network = graph_state.get_network(network_id)
    if network is None:
        raise HTTPException(status_code=404, detail="Network not found")
    node = network.graph.get_node_by_id(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    run_id = WorkflowManager.instance().start(
        graph_state=graph_state,
        network_id=network_id,
        node_id=node_id,
        step=step,
    )
    return {"status": "ok", "runId": run_id}


# ── GET /executions/:runId/waiting ──────────────────────────────────────────────────
# Returns the nodes currently paused on WAIT within a running execution.
# Call this after receiving a HUMAN_INPUT_REQUIRED trace event to get
# the node id and prompt before POSTing the human's response.

@router.get("/executions/{run_id}/waiting")
async def get_waiting_nodes(run_id: str) -> Dict[str, Any]:
    waiting = WorkflowManager.instance().get_waiting_nodes(run_id)
    if waiting is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active execution with runId '{run_id}'",
        )
    return {"runId": run_id, "waitingNodes": waiting}


# ── POST /executions/:runId/nodes/:nodeId/cancel-sampling ─────────────────────
# Signal a running KSamplerNode to stop after the current denoising step.
# The node will emit a SAMPLING_CANCELLED trace event and continue with whatever
# latent it has so far — downstream VAEDecode / SaveImage still run normally.
#
#   curl -X POST http://localhost:3001/api/executions/<run_id>/nodes/<node_id>/cancel-sampling

@router.post("/executions/{run_id}/nodes/{node_id}/cancel-sampling")
async def cancel_sampling(run_id: str, node_id: str) -> Dict[str, Any]:
    executor = graph_state.active_executors.get(run_id)
    if executor is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active execution with runId '{run_id}'",
        )
    node = executor.graph.get_node_by_id(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    cancel_event = getattr(node, "_cancel_event", None)
    if cancel_event is None:
        raise HTTPException(
            status_code=400,
            detail=f"Node '{node_id}' does not support sampling cancellation",
        )
    cancel_event.set()
    print(f"[cancel-sampling] run={run_id} node={node_id} — cancellation requested", flush=True)
    return {"ok": True, "runId": run_id, "nodeId": node_id}


# ── Graph save / load ─────────────────────────────────────────────────────────

import json as _json
import re as _re

_SAVES_DIR = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")), "saves"
)
_SAFE_NAME_RE = _re.compile(r'^[\w\- ]{1,80}$')


def _saves_dir() -> str:
    os.makedirs(_SAVES_DIR, exist_ok=True)
    return _SAVES_DIR


def _save_path(name: str) -> str:
    return os.path.join(_saves_dir(), f"{name}.json")


@router.get("/graphs")
async def list_graphs() -> List[Dict[str, Any]]:
    """Return meta-data for all saved graph files."""
    saves_dir = _saves_dir()
    result = []
    for fname in sorted(os.listdir(saves_dir)):
        if not fname.endswith(".json"):
            continue
        name = fname[:-5]
        fpath = os.path.join(saves_dir, fname)
        stat = os.stat(fpath)
        result.append({"name": name, "savedAt": int(stat.st_mtime * 1000)})
    return result


class SaveGraphBody(BaseModel):
    name: str


@router.post("/graphs", status_code=201)
async def save_graph(body: SaveGraphBody) -> List[Dict[str, Any]]:
    """Serialize the current graph state to *saves/{name}.json*."""
    name = body.name.strip()
    if not name or not _SAFE_NAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Graph name must be 1–80 alphanumeric / dash / space characters",
        )
    snapshot = graph_state.to_snapshot()
    fpath = _save_path(name)
    with open(fpath, "w", encoding="utf-8") as fh:
        _json.dump(snapshot, fh, indent=2)
    print(f"[graph-save] saved '{name}' → {fpath}", flush=True)
    return await list_graphs()


@router.post("/graphs/{name}/load")
async def load_graph(name: str) -> Dict[str, Any]:
    """Load *saves/{name}.json* and replace the running graph state."""
    # Sanitise: only allow names that already exist as files
    fpath = _save_path(name)
    if not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail=f"No saved graph named '{name}'")
    with open(fpath, "r", encoding="utf-8") as fh:
        snapshot = _json.load(fh)
    try:
        graph_state.load_snapshot(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load graph: {exc}")
    print(f"[graph-load] loaded '{name}' from {fpath}", flush=True)
    net = graph_state.root_network
    return {"id": net.id, "name": net.name}
