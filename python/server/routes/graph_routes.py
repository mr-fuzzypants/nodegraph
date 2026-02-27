"""
Graph REST routes — Python port of server/src/routes/graphRoutes.ts.

All routes are mounted under /api by main.py.
"""
from __future__ import annotations

import sys
import os
import asyncio
import json
import time
import traceback
import uuid as _uuid_module

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nodegraph.python.core.Executor import Executor
from nodegraph.python.core.DurabilityBackend import DBOSBackend
from nodegraph.python.server.serializers.graph_serializer import serialize_network
from nodegraph.python.server.state import graph_state
from nodegraph.python.server.trace.trace_emitter import global_tracer

# ── DBOS import (optional — degrades gracefully when DB not configured) ───────
try:
    from dbos import DBOS as _DBOS
    _dbos_available = True
except ImportError:
    _DBOS = None  # type: ignore
    _dbos_available = False

# ── Module-level DBOS step + workflow ───────────────────────────────────
# Both must be module-level (not closures) so DBOS can locate them by stable
# function identity after a process restart and replay from last checkpoint.
# Step-through (debug) mode is NOT available on the durable path.
_graph_execution_workflow = None
_execute_node_step = None

if _dbos_available:
    @_DBOS.step(name="nodegraph.execute_node_step")  # type: ignore[misc]
    async def _execute_node_step(  # type: ignore[misc]
        run_id: str, node_id: str, context: dict
    ) -> dict:
        """Durable step that executes one node's compute() and returns a
        JSON-serialisable dict.  DBOS saves the return value to the DB so on
        process restart the step is skipped and the saved result is returned
        immediately — giving exactly-once execution for expensive/side-effectful
        nodes (LLM calls, human-in-the-loop waits, etc.).
        """
        executor = graph_state.active_executors.get(run_id)
        if executor is None:
            raise RuntimeError(f"[execute_node_step] No active executor for run_id={run_id!r}")
        node = executor.graph.get_node_by_id(node_id)
        if node is None:
            raise RuntimeError(f"[execute_node_step] Node {node_id!r} not found in run {run_id!r}")
        result = await node.compute(executionContext=context)
        return {
            "command":         result.command.name,
            "data_outputs":    result.data_outputs,
            "control_outputs": result.control_outputs,
        }

    @_DBOS.workflow(name="nodegraph.run_graph")  # type: ignore[misc]
    async def _graph_execution_workflow(  # type: ignore[misc]
        run_id: str, network_id: str, node_id: str
    ) -> None:
        network = graph_state.get_network(network_id)
        if network is None:
            return
        node = network.graph.get_node_by_id(node_id)
        if node is None:
            return

        executor = Executor(network.graph)
        executor._sequential_batches = True  # deterministic replay order inside DBOS
        executor.run_id = run_id
        executor.backend = DBOSBackend(step_fn=_execute_node_step)  # exactly-once via DBOS
        graph_state.active_executors[run_id] = executor

        # ── on_checkpoint: persist scheduler stack state after each batch ─────
        # Writes execution_stack / pending_stack / deferred_stack as a JSON
        # sidecar file so in-flight state survives non-DBOS restarts and is
        # inspectable for debugging.  The DBOS step-replay mechanism handles
        # node-level durability independently.
        _cp_dir = os.path.join(os.path.dirname(__file__), "..", "checkpoints")
        os.makedirs(_cp_dir, exist_ok=True)
        _cp_path = os.path.join(_cp_dir, f"{run_id}.json")
        def _write_checkpoint(cp: dict) -> None:
            with open(_cp_path, "w") as _f:
                json.dump(cp, _f)
        executor.on_checkpoint = _write_checkpoint

        # ── Trace hooks — fire NODE_RUNNING / NODE_DONE / EDGE_ACTIVE / NODE_RESUMED
        # events for the UI. (step-through mode unavailable on the durable path)
        def _before(nid: str, name: str = "") -> None:
            global_tracer.fire({"type": "NODE_RUNNING", "nodeId": nid})

        def _after(nid: str, name: str, duration_ms: float, error: Optional[str] = None) -> None:
            if error:
                global_tracer.fire({"type": "NODE_ERROR", "nodeId": nid, "error": error})
            else:
                global_tracer.fire({"type": "NODE_DONE", "nodeId": nid, "durationMs": duration_ms})

        def _edge(fid: str, fp: str, tid: str, tp: str) -> None:
            global_tracer.fire(
                {"type": "EDGE_ACTIVE", "fromNodeId": fid, "fromPort": fp,
                 "toNodeId": tid, "toPort": tp}
            )

        def _waiting(nid: str, name: str = "") -> None:
            global_tracer.fire({"type": "NODE_RESUMED", "nodeId": nid})

        executor.on_before_node  = _before
        executor.on_after_node   = _after
        executor.on_edge_data    = _edge
        executor.on_node_waiting = _waiting

        try:
            if node.is_flow_control_node:
                await executor.cook_flow_control_nodes(node)
            else:
                await executor.cook_data_nodes(node)
        finally:
            graph_state.active_executors.pop(run_id, None)
            # Clean up checkpoint sidecar on successful completion.
            try:
                os.remove(_cp_path)
            except FileNotFoundError:
                pass

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

    run_id = _uuid_module.uuid4().hex

    if step:
        global_tracer.enable_step()

    global_tracer.fire(
        {"type": "EXEC_START", "networkId": network_id, "rootNodeId": node_id, "runId": run_id}
    )

    async def _run() -> None:
        """Background coroutine — runs execution without blocking the HTTP response."""
        try:
            if _dbos_available and _graph_execution_workflow is not None and not step:
                # ── Durable path ───────────────────────────────────────────────
                # Use the async variants: start_workflow_async returns a
                # WorkflowHandleAsync whose get_result() is awaitable and
                # non-blocking (start_workflow / WorkflowHandle.get_result are
                # both synchronous and would block the event loop).
                handle = await _DBOS.start_workflow_async(_graph_execution_workflow, run_id, network_id, node_id)
                await handle.get_result()
            else:
                # ── Non-durable path (step mode, or DBOS not configured) ──────
                executor = Executor(network.graph)
                graph_state.active_executors[run_id] = executor

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

                def _on_node_waiting(exec_node_id: str, name: str = "") -> None:
                    global_tracer.fire({"type": "NODE_RESUMED", "nodeId": exec_node_id})

                executor.on_before_node  = _on_before_node
                executor.on_after_node   = _on_after_node
                executor.on_edge_data    = _on_edge_data
                executor.on_node_waiting = _on_node_waiting

                try:
                    if node.is_flow_control_node:
                        await executor.cook_flow_control_nodes(node)
                    else:
                        await executor.cook_data_nodes(node)
                finally:
                    graph_state.active_executors.pop(run_id, None)

            global_tracer.fire({"type": "EXEC_DONE", "networkId": network_id, "runId": run_id})
        except Exception as exc:
            tb = traceback.format_exc()
            print(f"[execute] ERROR:\n{tb}", flush=True)
            global_tracer.fire(
                {"type": "EXEC_ERROR", "networkId": network_id, "error": str(exc), "runId": run_id}
            )
        finally:
            if step:
                global_tracer.disable_step()

    # Schedule execution in the background — the HTTP response returns
    # immediately so the client stays unblocked while the graph runs.
    # Trace events (including HUMAN_INPUT_REQUIRED) flow via WebSocket.
    asyncio.create_task(_run())

    return {"status": "ok", "runId": run_id}


# ── GET /executions/:runId/waiting ──────────────────────────────────────────────────
# Returns the nodes currently paused on WAIT within a running execution.
# Call this after receiving a HUMAN_INPUT_REQUIRED trace event to get
# the node id and prompt before POSTing the human's response.

@router.get("/executions/{run_id}/waiting")
async def get_waiting_nodes(run_id: str) -> Dict[str, Any]:
    executor = graph_state.active_executors.get(run_id)
    if executor is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active execution with runId '{run_id}'",
        )
    waiting = []
    for node_id in list(executor.waiting_nodes.keys()):
        node = executor.graph.get_node_by_id(node_id)
        waiting.append({
            "nodeId": node_id,
            "prompt": node.inputs["prompt"].value if node and "prompt" in node.inputs else "",
        })
    return {"runId": run_id, "waitingNodes": waiting}
