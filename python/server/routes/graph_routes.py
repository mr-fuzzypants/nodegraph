"""
Graph REST routes — Python port of server/src/routes/graphRoutes.ts.

All routes are mounted under /api by main.py.
"""
from __future__ import annotations

import sys
import os
import time
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nodegraph.python.core.Executor import Executor
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
        return serialize_network(network, graph_state.positions)
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
        graph_state.add_tunnel_port(network_id, body.name.strip(), body.direction)
        network = graph_state.get_network(network_id)
        return serialize_network(network, graph_state.positions)
    except HTTPException:
        raise
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


# ── GET /node-types ───────────────────────────────────────────────────────────

@router.get("/node-types")
async def get_node_types() -> List[str]:
    from nodegraph.python.core.Node import Node

    return list(Node._node_registry.keys()) if Node._node_registry else []


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

    executor = Executor(network.graph)

    if step:
        global_tracer.enable_step()

    global_tracer.fire(
        {"type": "EXEC_START", "networkId": network_id, "rootNodeId": node_id}
    )

    # ── Wire executor hooks ───────────────────────────────────────────────

    async def _on_before_node(exec_node_id: str, name: str = "") -> None:
        if step:
            global_tracer.fire({"type": "STEP_PAUSE", "nodeId": exec_node_id})
            await global_tracer.wait_for_step()
        global_tracer.fire({"type": "NODE_RUNNING", "nodeId": exec_node_id})

    def _on_after_node(
        exec_node_id: str,
        name: str,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        if error:
            global_tracer.fire(
                {"type": "NODE_ERROR", "nodeId": exec_node_id, "error": error}
            )
        else:
            global_tracer.fire(
                {"type": "NODE_DONE", "nodeId": exec_node_id, "durationMs": duration_ms}
            )

    def _on_edge_data(
        from_node_id: str, from_port: str, to_node_id: str, to_port: str
    ) -> None:
        global_tracer.fire(
            {
                "type": "EDGE_ACTIVE",
                "fromNodeId": from_node_id,
                "fromPort": from_port,
                "toNodeId": to_node_id,
                "toPort": to_port,
            }
        )

    executor.on_before_node = _on_before_node
    executor.on_after_node = _on_after_node
    executor.on_edge_data = _on_edge_data

    # ─────────────────────────────────────────────────────────────────────

    try:
        if node.is_flow_control_node:
            await executor.cook_flow_control_nodes(node)
        else:
            await executor.cook_data_nodes(node)
        global_tracer.fire({"type": "EXEC_DONE", "networkId": network_id})
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[execute] ERROR:\n{tb}", flush=True)
        global_tracer.fire(
            {"type": "EXEC_ERROR", "networkId": network_id, "error": str(exc)}
        )
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if step:
            global_tracer.disable_step()

    return {"status": "ok"}
