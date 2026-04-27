"""
WorkflowManager — owns the full lifecycle of a graph execution run.

Responsibilities
----------------
- Building and configuring the Executor (single implementation for both paths)
- Wiring all trace hooks (NODE_RUNNING / NODE_DONE / EDGE_ACTIVE / NODE_RESUMED)
- Selecting durable (DBOS) vs non-durable vs step-through execution path
- Registering / deregistering active runs in active_executors
- Writing checkpoint sidecars on the durable path
- Exposing run status / waiting-node queries for HTTP routes

graph_routes.py becomes pure HTTP after this refactor:
  - parse request
  - call WorkflowManager.instance().start(...)
  - return response
"""
from __future__ import annotations

import asyncio
import json
import os
import traceback
import uuid as _uuid_module
from typing import Any, Dict, List, Optional

# ── DBOS (optional — degrades gracefully) ─────────────────────────────────────
try:
    from dbos import DBOS as _DBOS
    _dbos_available = True
except ImportError:
    _DBOS = None          # type: ignore
    _dbos_available = False

try:
    from nodegraph.python.core.DurabilityBackend import DBOSBackend
except ImportError:
    DBOSBackend = None    # type: ignore

from nodegraph.python.core.Executor import Executor


# ── Module-level DBOS step + workflow ─────────────────────────────────────────
# Must be at module level (not closures) so DBOS can locate them via stable
# function identity after a process restart and replay from last checkpoint.
# Step-through (debug) mode is NOT available on the durable path.

_execute_node_step        = None
_graph_execution_workflow = None

if _dbos_available:
    @_DBOS.step(name="nodegraph.execute_node_step")   # type: ignore[misc]
    async def _execute_node_step(
        run_id: str, node_id: str, context: dict
    ) -> dict:
        """Durable step that executes one node's compute() and returns a
        JSON-serialisable dict.  DBOS saves the return value to the DB so on
        process restart the step is skipped and the saved result is returned
        immediately — giving exactly-once execution for expensive/side-effectful
        nodes (LLM calls, human-in-the-loop waits, etc.).
        """
        executor = WorkflowManager.instance().active_executors.get(run_id)
        if executor is None:
            raise RuntimeError(
                f"[execute_node_step] No active executor for run_id={run_id!r}"
            )
        node = executor.graph.get_node_by_id(node_id)
        if node is None:
            raise RuntimeError(
                f"[execute_node_step] Node {node_id!r} not found in run {run_id!r}"
            )
        if getattr(context, "env", None) is None:
            try:
                context.env = executor.env
            except AttributeError:
                from nodegraph.python.core.node_context import NodeContext
                context = NodeContext.from_dict(context, env=executor.env)
        result = await node.compute(executionContext=context)
        return {
            "command":         result.command.name,
            "data_outputs":    result.data_outputs,
            "control_outputs": result.control_outputs,
        }

    @_DBOS.workflow(name="nodegraph.run_graph")       # type: ignore[misc]
    async def _graph_execution_workflow(
        run_id: str, network_id: str, node_id: str
    ) -> None:
        await WorkflowManager.instance()._run_executor(
            run_id=run_id,
            network_id=network_id,
            node_id=node_id,
            step=False,
            durable=True,
        )


# ─────────────────────────────────────────────────────────────────────────────

class WorkflowManager:
    """
    Singleton.  Obtain via ``WorkflowManager.instance()``.

    Public API
    ----------
    start(graph_state, network_id, node_id, step) -> run_id
        Kick off a graph execution asynchronously.  Returns the run_id
        immediately so the HTTP layer can respond without blocking.

    get_executor(run_id) -> Optional[Executor]
        Return the live Executor for an in-progress run, or None.

    get_waiting_nodes(run_id) -> Optional[List[dict]]
        Return waiting-node info for /executions/:runId/waiting, or None.
    """

    _instance: "WorkflowManager | None" = None

    @classmethod
    def instance(cls) -> "WorkflowManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        # run_id → Executor (populated while the run is active)
        # Kept as a plain dict so the DBOS step and the human-input route can
        # look up the executor without going through the HTTP layer.
        self.active_executors: Dict[str, Executor] = {}

        self._checkpoint_dir = os.path.join(
            os.path.dirname(__file__), "..", "server", "checkpoints"
        )
        self._diffusion_backend: Any = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(
        self,
        graph_state: Any,
        network_id: str,
        node_id: str,
        step: bool = False,
    ) -> str:
        """
        Kick off a graph run in the background.  Returns run_id immediately.

        Parameters
        ----------
        graph_state : server GraphState singleton
        network_id  : id of the NodeNetwork to execute
        node_id     : id of the root node (execution entry point)
        step        : True → step-through (debug) mode; incompatible with DBOS
        """
        # Lazy import to avoid circular dependency with server.state
        from nodegraph.python.server.trace.trace_emitter import global_tracer

        run_id = _uuid_module.uuid4().hex

        if step:
            global_tracer.enable_step()

        global_tracer.fire({
            "type":       "EXEC_START",
            "networkId":  network_id,
            "rootNodeId": node_id,
            "runId":      run_id,
        })

        asyncio.create_task(self._dispatch(graph_state, run_id, network_id, node_id, step))
        return run_id

    def get_executor(self, run_id: str) -> Optional[Executor]:
        """Return the live Executor for a run, or None if not active."""
        return self.active_executors.get(run_id)

    def get_waiting_nodes(self, run_id: str) -> Optional[List[dict]]:
        """
        Return waiting-node descriptors for /executions/:runId/waiting.
        Returns None when the run_id is not found.
        """
        executor = self.active_executors.get(run_id)
        if executor is None:
            return None
        waiting = []
        for nid in list(executor.waiting_nodes.keys()):
            node = executor.graph.get_node_by_id(nid)
            waiting.append({
                "nodeId": nid,
                "prompt": (
                    node.inputs["prompt"].value
                    if node and "prompt" in node.inputs
                    else ""
                ),
            })
        return waiting

    def _create_node_environment(self, run_id: str) -> Any:
        """Build runtime resources shared by nodes in one graph execution."""
        from nodegraph.python.core.node_context import NodeEnvironment
        from nodegraph.python.server.trace.trace_emitter import global_tracer

        class TraceEventBus:
            async def publish(self, event: dict) -> None:
                global_tracer.fire(event)

            async def close(self) -> None:
                pass

        try:
            from nodegraph.python.core.backends.safetensors_backend import SafetensorsBackend
        except ImportError as exc:
            print(f"[WorkflowManager] diffusion backend unavailable: {exc}", flush=True)
            return NodeEnvironment(trace_id=run_id, event_bus=TraceEventBus())

        if self._diffusion_backend is None:
            device = os.environ.get("NODEGRAPH_DIFFUSION_DEVICE") or self._detect_diffusion_device()
            dtype = os.environ.get("NODEGRAPH_DIFFUSION_DTYPE") or (
                "float32" if device == "cpu" else "float16"
            )
            self._diffusion_backend = SafetensorsBackend(device=device, dtype=dtype)
            print(
                f"[WorkflowManager] diffusion backend ready device={device} dtype={dtype}",
                flush=True,
            )

        return NodeEnvironment(
            backend=self._diffusion_backend,
            trace_id=run_id,
            event_bus=TraceEventBus(),
        )

    @staticmethod
    def _detect_diffusion_device() -> str:
        try:
            import torch  # type: ignore
        except ImportError:
            return "cpu"

        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _dispatch(
        self,
        graph_state: Any,
        run_id: str,
        network_id: str,
        node_id: str,
        step: bool,
    ) -> None:
        from nodegraph.python.server.trace.trace_emitter import global_tracer

        try:
            use_dbos = (
                _dbos_available
                and _graph_execution_workflow is not None
                and not step
            )

            if use_dbos:
                # ── Durable path ─────────────────────────────────────────────
                handle = await _DBOS.start_workflow_async(
                    _graph_execution_workflow,
                    run_id,
                    network_id,
                    node_id,
                )
                await handle.get_result()
            else:
                # ── Non-durable / step-through path ──────────────────────────
                await self._run_executor(
                    run_id=run_id,
                    network_id=network_id,
                    node_id=node_id,
                    step=step,
                    durable=False,
                    graph_state=graph_state,
                )

            global_tracer.fire({
                "type":      "EXEC_DONE",
                "networkId": network_id,
                "runId":     run_id,
            })

        except Exception as exc:
            print(
                f"[WorkflowManager] ERROR run={run_id}:\n{traceback.format_exc()}",
                flush=True,
            )
            global_tracer.fire({
                "type":      "EXEC_ERROR",
                "networkId": network_id,
                "error":     str(exc),
                "runId":     run_id,
            })

        finally:
            if step:
                from nodegraph.python.server.trace.trace_emitter import global_tracer as _gt
                _gt.disable_step()

    async def _run_executor(
        self,
        run_id: str,
        network_id: str,
        node_id: str,
        step: bool,
        durable: bool,
        graph_state: Any = None,
    ) -> None:
        """
        Single implementation of Executor construction, hook wiring, and
        teardown.  Used by both the durable and non-durable paths so there is
        no duplication.

        On the durable path graph_state is None (DBOS restored the process from
        a checkpoint) — we import the singleton directly in that case.
        """
        from nodegraph.python.server.trace.trace_emitter import global_tracer

        if graph_state is None:
            from nodegraph.python.server.state import graph_state as _gs
            graph_state = _gs

        network = graph_state.get_network(network_id)
        if network is None:
            return
        node = network.graph.get_node_by_id(node_id)
        if node is None:
            return

        executor = Executor(network.graph)
        executor.env = self._create_node_environment(run_id)

        # ── Durable-path configuration ────────────────────────────────────────
        cp_path: Optional[str] = None
        if durable:
            executor._sequential_batches = True
            executor.run_id  = run_id
            executor.backend = DBOSBackend(step_fn=_execute_node_step)  # type: ignore[arg-type]

            os.makedirs(self._checkpoint_dir, exist_ok=True)
            cp_path = os.path.join(self._checkpoint_dir, f"{run_id}.json")

            def _write_checkpoint(cp: dict) -> None:
                with open(cp_path, "w") as f:  # type: ignore[arg-type]
                    json.dump(cp, f)

            executor.on_checkpoint = _write_checkpoint

        # ── Register ─────────────────────────────────────────────────────────
        self.active_executors[run_id] = executor
        # Mirror onto graph_state so the human-input route can look up the
        # executor without importing WorkflowManager.
        graph_state.active_executors[run_id] = executor

        # ── Trace hooks (single implementation for both paths) ────────────────
        def _node_trace_fields(exec_node_id: str, name: str = "") -> dict:
            fields = {
                "networkId": network_id,
                "nodeName": name,
            }
            try:
                path = executor.graph.get_path(exec_node_id)
            except Exception:
                path = None
            if path:
                fields["nodePath"] = path
            return fields

        async def _on_before_node(exec_node_id: str, name: str = "") -> None:
            if step:
                global_tracer.fire({"type": "STEP_PAUSE", "nodeId": exec_node_id})
                await global_tracer.wait_for_step()
            global_tracer.fire({
                "type": "NODE_RUNNING",
                "nodeId": exec_node_id,
                **_node_trace_fields(exec_node_id, name),
            })

        def _on_after_node(
            exec_node_id: str,
            name: str,
            duration_ms: float,
            error: Optional[str] = None,
        ) -> None:
            fields = _node_trace_fields(exec_node_id, name)
            if error:
                global_tracer.fire(
                    {
                        "type": "NODE_ERROR",
                        "nodeId": exec_node_id,
                        "durationMs": duration_ms,
                        "error": error,
                        **fields,
                    }
                )
            else:
                global_tracer.fire(
                    {
                        "type": "NODE_DONE",
                        "nodeId": exec_node_id,
                        "durationMs": duration_ms,
                        **fields,
                    }
                )

        def _on_edge_data(
            from_node_id: str, from_port: str, to_node_id: str, to_port: str
        ) -> None:
            global_tracer.fire({
                "type":       "EDGE_ACTIVE",
                "fromNodeId": from_node_id,
                "fromPort":   from_port,
                "toNodeId":   to_node_id,
                "toPort":     to_port,
            })

        def _on_node_waiting(exec_node_id: str, name: str = "") -> None:
            global_tracer.fire({"type": "NODE_RESUMED", "nodeId": exec_node_id})

        executor.on_before_node  = _on_before_node
        executor.on_after_node   = _on_after_node
        executor.on_edge_data    = _on_edge_data
        executor.on_node_waiting = _on_node_waiting

        # ── Run ───────────────────────────────────────────────────────────────
        try:
            if node.is_flow_control_node:
                await executor.cook_flow_control_nodes(node)
            else:
                await executor.cook_data_nodes(node)
        finally:
            self.active_executors.pop(run_id, None)
            graph_state.active_executors.pop(run_id, None)
            if cp_path:
                try:
                    os.remove(cp_path)
                except FileNotFoundError:
                    pass
