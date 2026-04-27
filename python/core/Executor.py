import asyncio
from typing import Optional, List, Dict, Any, Type, Callable, TYPE_CHECKING, Tuple, Set
from enum import Enum, auto
from logging import getLogger

from .Node import Node
from .GraphPrimitives import Graph, Edge
from .Types import PortDirection, PortFunction, NodeKind
from .Interface import IExecutionContext, IExecutionResult
from .DurabilityBackend import NullBackend
from .node_context import NodeContext, NodeEnvironment

logger = getLogger(__name__)

class ExecCommand(Enum):
    CONTINUE = auto()   # Scheduler: Add 'next_nodes' to the execution queue
    WAIT = auto()       # Scheduler: Pause execution (e.g. await Promise)
    LOOP_AGAIN = auto() # Scheduler: Re-schedule this node immediately (for iterative loops)
    COMPLETED = auto()  # Scheduler: Stop this branch of execution

class ExecutionResult(IExecutionResult):
    """
    Standardized return type for all Node execution. 
    Decouples the logic (Node) from the flow control (Runner).
    """
    def __init__(self, command: ExecCommand,  control_outputs: Optional[Dict[str, Any]] = None):
        self.command = command
        #self.next_nodes = [] #next_nodes if next_nodes is not None else []
        #self.next_node_ids = [] #next_node_ids if next_node_ids is not None else []
        self.network_id= ""
        self.node_id = ""
        self.node_path = ""
        self.uuid = ""
        self.data_outputs = {}
        # TODOL why?
        self.control_outputs = control_outputs if control_outputs is not None else {}

    
    def deserialize_result(self, node):
        #TODO (1): we may want to have a more formal way of returning 
        #TODO:  output values and updating ports.
        for output_name, output_value in self.data_outputs.items():
            out_port = node.outputs.get(output_name)
            if out_port:
                out_port.value = output_value
                out_port._isDirty = False

        #TODO (2): we may want to have a more formal way of returning 
        #TODO:  output values and updating ports.
        for output_name, output_value in self.control_outputs.items():
            out_port = node.outputs.get(output_name)
            if out_port:
                out_port.value = output_value
                out_port._isDirty = False
        node.markClean()


class ExecutionContext(IExecutionContext):
    """
    Context object passed to nodes during execution.
    Can hold references to the network, global state, etc.
    """
    def __init__(self, node: 'Node'):
        self.node = node
        self.network_id = node.network_id
        self.data_inputs = {}
        self.data_outputs = {}

    def get_port_value(self, port) -> Any:
        #assert(port._isDirty == False), f"Port '{port.port_name}' value is dirty '{port._isDirty}'. Current value: {port.value}"
        
        return port.value   # this seems to work properly, but we need to verify that the value is being properly propagated through the network and that dirty flags are being respected.

        # TODO: check for sure we don't need this.
        """
        if not self.node.graph:
             raise ValueError(f"Node {self.node.id} has no graph context")

        incoming_edges = self.node.graph.get_incoming_edges(port.node_id, port.port_name)
      
        if not incoming_edges:
            return port.value
        
        edge = incoming_edges[0]
        
        source_node = self.node.graph.get_node_by_id(edge.from_node_id)
        
        if source_node.isNetwork():
            # Check outputs first (Standard Node behavior)
            source_port = source_node.outputs.get(edge.from_port_name)
            if not source_port:
                # Fallback to inputs (Tunneling/Passthrough for Network Nodes)
                source_port = source_node.inputs.get(edge.from_port_name)
        else:
            source_port = source_node.outputs.get(edge.from_port_name)  

        if source_port is None:
            raise ValueError(f"Source port '{edge.from_port_name}' not found on node '{source_node.id}'")   
        
        assert(self.node.graph is not None), "Node must have a graph context to get port values"
        
        return source_port.value
    """

    def to_dict(self) -> Dict[str, Any]:
        print(".     [1.5]Building execution context for node:", self.node.id, self.node.type)
        data_inputs = {}
        control_inputs = {}
        for port_name, port in self.node.inputs.items():
            if port.isDataPort():
                data_inputs[port_name] = self.get_port_value(port)
            elif port.isControlPort():
                control_inputs[port_name] = self.get_port_value(port)

        result = {
            "uuid": self.node.uuid,
            "network_id": self.network_id,
            "node_id": self.node.id,
            "node_path": self.node.path,
            "data_inputs": data_inputs,
            "control_inputs": control_inputs
        }

        return result

    def from_dict(self, context_dict: Dict[str, Any]):
        for port_name, value in context_dict.get("data_inputs", {}).items():
            port = self.node.inputs.get(port_name)
            port.value = value
            port._isDirty = False

        for port_name, value in context_dict.get("control_inputs", {}).items():
            port = self.node.inputs.get(port_name)
            port.value = value
            port._isDirty = False   


# TODO: This has not been finished yet, but the idea is that we 
# TODO: can use this to keep track of pending nodes and their dependencies 
# TODO: during cooking, so we can determine the correct execution order. 
# TODO: This is especially important for flow control nodes where the
# TODO: execution order is not strictly determined by data dependencies.
class PendingStackEntry:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.dependencies: List[str] = []  # List of node IDs that must be executed before this node

    def add_dependency(self, node_id: str):
        if node_id not in self.dependencies:
            self.dependencies.append(node_id)

    def remove_dependency(self, node_id: str):
        if node_id in self.dependencies:
            self.dependencies.remove(node_id)

class PendingStack:
    def __init__(self):
        self.stack: Dict[str, PendingStackEntry] = {}

    def add_node(self, node_id: str):
        if node_id not in self.stack:
            self.stack[node_id] = PendingStackEntry(node_id)

    def add_dependency(self, node_id: str, dependency_id: str):
        self.add_node(node_id)
        self.stack[node_id].add_dependency(dependency_id)

    def remove_dependency(self, node_id: str, dependency_id: str):
        if node_id in self.stack:
            self.stack[node_id].remove_dependency(dependency_id)
            if not self.stack[node_id].dependencies:
                del self.stack[node_id]
    def get_ready_nodes(self) -> List[str]:
        return [node_id for node_id, entry in self.stack.items() if not entry.dependencies]
    


class Executor:
    def __init__(self, graph: Graph):
        self.graph = graph

        # ── Observation hooks (optional) ──────────────────────────────────
        # Set these before calling cook_* to receive lifecycle events.
        #
        # on_before_node(node_id: str, name: str) -> None | Awaitable[None]
        #   Called just before a node's compute() is invoked.  May be async.
        self.on_before_node = None

        # on_after_node(node_id: str, name: str, duration_ms: float, error: str|None) -> None
        #   Called after compute() returns (or raises).  Always synchronous.
        self.on_after_node = None

        # on_edge_data(from_node_id, from_port, to_node_id, to_port) -> None
        #   Called each time a data value is pushed along an edge.
        self.on_edge_data = None

        # on_checkpoint(checkpoint: dict) -> None
        #   Called after each scheduling batch completes with a serialisable
        #   snapshot of the current execution state.  May be async.
        #   Keys: 'batch_ids', 'execution_stack', 'pending_stack', 'deferred_stack'.
        self.on_checkpoint = None

        # _sequential_batches: bool
        #   When True, nodes in each batch are executed sequentially (await one
        #   by one) rather than in parallel via asyncio.gather.  Set True when
        #   running inside a DBOS workflow so that node execution order is
        #   deterministic and can be replayed identically after a crash.
        self._sequential_batches: bool = False

        # on_node_waiting(node_id: str, name: str) -> None | Awaitable[None]
        #   Called when a node returns ExecCommand.WAIT (after compute() has already
        #   unblocked — the human responded and routing is about to proceed).
        #   May be async.  Use this to emit NODE_RESUMED trace events.
        self.on_node_waiting = None

        # waiting_nodes: node_id → ExecutionResult
        #   Populated while processing a WAIT result so callers (e.g. API endpoints)
        #   can inspect which nodes have just been waited upon within this execution.
        self.waiting_nodes: Dict[str, "ExecutionResult"] = {}

        # run_id: str | None
        #   Set by the route handler when running inside a DBOS workflow so that
        #   the backend can associate this executor with a specific workflow run.
        self.run_id: Optional[str] = None

        # backend: DurabilityBackend
        #   Pluggable execution backend for nodes whose is_durable_step flag is True.
        #   Defaults to NullBackend (calls compute() directly — no persistence).
        #   Swap for FileBackend (local replay) or DBOSBackend (exactly-once via DBOS)
        #   by setting executor.backend before calling cook_*.
        #   See python/core/DurabilityBackend.py for available backends.
        self.backend: Any = NullBackend()

        # env: NodeEnvironment | None
        #   Process-local, non-serialisable runtime resources (diffusion backend,
        #   tensor store, event bus).  Set this before calling cook_* when running
        #   imaging or other env-aware nodes.
        #   Attached to each NodeContext so nodes can access env via
        #   ``executionContext.env.backend`` without a second compute() kwarg.
        self.env: Optional[NodeEnvironment] = None

    async def cook_flow_control_nodes(self, node: Node, execution_stack: List[str]=None, pending_stack: Dict[str, List[str]]=None )-> None:
        # New implementation with Stack (LIFO) and Deferred Execution for Loops
        
        if execution_stack is None:
            execution_stack = []
        if pending_stack is None:
            pending_stack = {}
    
        # Store nodes that requested to loop again here, 
        # preventing them from running until the current stack is empty.
        deferred_stack = []

        if node.isFlowControlNode():
            self.build_flow_node_execution_stack(node, execution_stack, pending_stack)
            
        for node_id in list(pending_stack.keys()):
            deps = pending_stack[node_id]
            if len(deps) == 0:
                execution_stack.append(node_id)
                del pending_stack[node_id]
        
        while execution_stack or deferred_stack:
            
            # 1. Automatic "Next Iteration" Loading
            # If the main stack is empty (body finished), reload only the innermost
            # (most recently deferred) loop node via LIFO pop.
            #
            # Why LIFO and not extend+clear?
            # In nested loops, deferred_stack accumulates one entry per nesting level
            # (e.g. [outer_loop, inner_loop]).  When the inner body finishes the
            # execution_stack empties, but the outer loop must stay deferred until
            # the inner loop has fully exited (stopped returning LOOP_AGAIN).
            # Popping only the last entry reloads the innermost loop; the outer loop
            # remains in deferred and is reloaded only after the inner loop exits.
            if not execution_stack and deferred_stack:
                execution_stack.append(deferred_stack.pop())

            # 2. Parallel Batch Collection
            # Pop EVERYTHING currently in the stack. 
            # Since dependencies are already resolved by 'pending_stack', 
            # all nodes in 'execution_stack' are theoretically ready to run.
            batch_ids = execution_stack[:] 
            execution_stack.clear()
            
            # 3. Parallel or Sequential Execution
            # Sequential mode is used inside DBOS workflows for deterministic
            # replay — same node execution order on every run.
            if not batch_ids: continue

            if self._sequential_batches:
                results = []
                for nid in batch_ids:
                    results.append(await self._execute_single_node(nid))
            else:
                tasks = [self._execute_single_node(nid) for nid in batch_ids]
                results = await asyncio.gather(*tasks)

            # 4. Result Processing (Sequential update of graph state)
            for (cur_node, result) in results:
                if not cur_node or not result: continue

                # A. Handle Loop Backs (Deferred)
                # Use name check to avoid Enum identity issues with module reloading/path issues in tests
                if result.command.name == "LOOP_AGAIN":
                    deferred_stack.append(cur_node.id)

                # A2. Handle WAIT — node's compute() has already unblocked (the
                # asyncio.Event was set before compute() returned).  Record that
                # this node was awaited and fire the on_node_waiting hook so the
                # route handler can emit a NODE_RESUMED trace event.  Routing then
                # proceeds normally via _process_control_outputs.
                elif result.command.name == "WAIT":
                    self.waiting_nodes[cur_node.id] = result
                    if self.on_node_waiting is not None:
                        ret = self.on_node_waiting(cur_node.id, cur_node.name)
                        if ret is not None and hasattr(ret, "__await__"):
                            await ret

                # B + C. NEW: AgentExecutor changes — inlined routing logic moved to
                # _process_control_outputs() so subclasses can override only routing
                # without touching node execution, data propagation, or loop handling.
                await self._process_control_outputs(  # NEW: AgentExecutor changes
                    cur_node, result, execution_stack, pending_stack  # NEW: AgentExecutor changes
                )  # NEW: AgentExecutor changes

                # Clean up WAIT tracking after routing so waiting_nodes reflects
                # only nodes that are currently being processed (not historical).
                self.waiting_nodes.pop(cur_node.id, None)
            
            # 5. Promote Ready Nodes from Pending to Stack
            # (Queueing them for the NEXT batch)
            # Check dependency stack one last time to see who became ready
            for node_id in list(pending_stack.keys()):
                deps = pending_stack[node_id]
                
                # Remove satisfied dependencies found in this batch
                for finished_id in batch_ids:
                    if finished_id in deps:
                         deps.remove(finished_id)

                if len(deps) == 0:
                    execution_stack.append(node_id) # Add to next batch
                    del pending_stack[node_id]

            # 5b. Deadlock guard — if no batch progress can unblock any pending
            # node and no deferred loops remain, the graph has an unresolvable
            # circular data dependency.  Raise a clear error rather than
            # silently exiting the while loop with nodes left stranded.
            if not execution_stack and not deferred_stack and pending_stack:
                lines = []
                for _nid, _deps in pending_stack.items():
                    _n     = self.graph.get_node_by_id(_nid)
                    _dnames = [
                        (self.graph.get_node_by_id(d).name
                         if self.graph.get_node_by_id(d) else d)
                        for d in _deps
                    ]
                    lines.append(
                        f"  '{_n.name if _n else _nid}' waiting on {_dnames}"
                    )
                raise RuntimeError(
                    "Graph deadlock: circular data dependency detected.\n"
                    "The following nodes cannot execute because their dependencies\n"
                    "form a cycle with no flow-control mediator (e.g. WhileLoopNode):\n"
                    + "\n".join(lines)
                )

            # 6. Checkpoint — serialise batch state for durability backends.
            # on_checkpoint receives the completed batch IDs, remaining stacks,
            # and the deferred stack so external handlers can persist progress.
            if self.on_checkpoint is not None:
                _checkpoint = {
                    "batch_ids":       list(batch_ids),
                    "execution_stack": list(execution_stack),
                    "pending_stack":   {k: list(v) for k, v in pending_stack.items()},
                    "deferred_stack":  list(deferred_stack),
                }
                _cp_ret = self.on_checkpoint(_checkpoint)
                if _cp_ret is not None and hasattr(_cp_ret, "__await__"):
                    await _cp_ret

        for node_id in pending_stack.keys():
            node = self.graph.get_node_by_id(node_id)
            node_name = node.name if node else "Unknown"
            print(f"Node '{node_name}' ({node_id}) still has dependencies: {pending_stack[node_id]}")
        
        if pending_stack:
            names = ", ".join(
                (self.graph.get_node_by_id(nid).name
                 if self.graph.get_node_by_id(nid) else nid)
                for nid in pending_stack
            )
            raise RuntimeError(
                f"cook_flow_control_nodes finished with unresolved nodes "
                f"still in pending_stack: {names}"
            )

    async def _execute_single_node(self, cur_node_id) -> Tuple[Optional[Node], Optional[ExecutionResult]]:
        """Helper to execute a single node safely within a gathered batch"""
        cur_node = self.graph.get_node_by_id(cur_node_id)
        
        if not cur_node: return (None, None)

        if cur_node.isNetwork():
            self.propogate_network_inputs_to_internal(cur_node)

        # Force Cook Upstream Data Dependencies (Recurisve lazy load)
        # This fixes regression where some data nodes are skipped by stack builder
        for input_port in cur_node.get_input_data_ports():
             upstream_nodes = self.get_upstream_nodes(input_port)
             for up_node in upstream_nodes:
                 if up_node.isDataNode() and up_node.isDirty():
                     # Recursively execute the dependency
                     await self._execute_single_node(up_node.id)

        print(f".   [1] Cooking node: {cur_node.name} ({cur_node_id})")
        print("     [1.1] Execution Context for node:", cur_node.name, ":", ExecutionContext(cur_node).to_dict())

        # ── on_before_node hook ───────────────────────────────────────────
        if self.on_before_node is not None:
            ret = self.on_before_node(cur_node.id, cur_node.name)
            if ret is not None and hasattr(ret, "__await__"):
                await ret

        context_dict = ExecutionContext(cur_node).to_dict()
        context = NodeContext.from_dict(context_dict, env=self.env)
        _t0 = asyncio.get_event_loop().time()
        try:
            # ── Durable step path ────────────────────────────────────────────
            # Nodes that opt in via is_durable_step=True are executed through
            # self.backend rather than compute() directly.  The backend is
            # responsible for persistence / replay semantics:
            #   NullBackend  — calls compute() directly (default, test-friendly)
            #   FileBackend  — JSON sidecar cache for local replay
            #   DBOSBackend  — exactly-once via DBOS step function
            if getattr(cur_node, "is_durable_step", False):
                raw = await self.backend.execute_node(
                    self.run_id, cur_node.id, context, cur_node.compute
                )
                result = ExecutionResult(ExecCommand[raw["command"]])
                result.data_outputs    = raw.get("data_outputs", {})
                result.control_outputs = raw.get("control_outputs", {})
            else:
                result = await cur_node.compute(executionContext=context)
        except Exception as _exc:
            _duration = (asyncio.get_event_loop().time() - _t0) * 1000
            if self.on_after_node is not None:
                self.on_after_node(
                    cur_node.id,
                    cur_node.name,
                    _duration,
                    f"{type(_exc).__name__}: {_exc}",
                )
            raise
        _duration = (asyncio.get_event_loop().time() - _t0) * 1000

        # Apply side effects immediately?
        # In strictly parallel systems we might buffer this, but here
        # we assume python's GIL/single-threaded async protects atomic port writes.
        result.deserialize_result(cur_node)

        # ── on_after_node hook ────────────────────────────────────────────
        if self.on_after_node is not None:
            self.on_after_node(cur_node.id, cur_node.name, _duration, None)

        if cur_node.isNetwork():
            self.propogate_internal_node_outputs_to_network(cur_node)

        self.push_data_from_node(cur_node)
            
        return (cur_node, result)
    
    

    # NEW: AgentExecutor changes ─────────────────────────────────────────────
    # Extracted verbatim from the B+C block previously inlined inside
    # cook_flow_control_nodes.  Making this a separate async method is the
    # only change needed to Executor to support AgentExecutor — everything
    # else (node execution, data propagation, loop handling, batching)
    # is inherited unchanged.
    async def _process_control_outputs(  # NEW: AgentExecutor changes
        self,
        cur_node: Node,
        result: ExecutionResult,
        execution_stack: List[str],
        pending_stack: Dict[str, List[str]],
    ) -> None:  # NEW: AgentExecutor changes
        """
        Resolves which nodes to schedule next from the control outputs fired by
        cur_node.  The base implementation follows static graph edges — identical
        to the logic previously inlined in cook_flow_control_nodes (B+C block).

        Override this method in subclasses (as async) to change routing behaviour.
        AgentExecutor overrides it to consult an LLM when no static successor
        exists.  Single-output / fully-connected nodes bypass the LLM entirely.
        """  # NEW: AgentExecutor changes
        # NEW: AgentExecutor changes — start of extracted B block
        connected_ids = []
        for control_name, control_value in result.control_outputs.items():
            print("     [**3] Control Output from node", cur_node.name, ":", control_name, "=", control_value)
            
            if control_value == True:
                print(f"     [**3.1] Control output '{control_name}' is True, routing to connected nodes...")
                edges = self.graph.get_outgoing_edges(cur_node.id, control_name)
                # TODO: need to propagate control output values as well I think.
                for edge in edges:
                    to_node = self.graph.get_node_by_id(edge.to_node_id)
                    if to_node:
                        if to_node.inputs.get(edge.to_port_name):
                            to_node.inputs[edge.to_port_name].setValue(control_value)
                        elif to_node.outputs.get(edge.to_port_name):
                            to_node.outputs[edge.to_port_name].setValue(control_value)

                next_ids = [e.to_node_id for e in edges if e.to_node_id != cur_node.network_id]
                connected_ids.extend(next_ids)
        # NEW: AgentExecutor changes — end of extracted B block, start of C block
        for next_node_id in connected_ids:
            next_node = self.graph.get_node_by_id(next_node_id)
            if next_node:
                self.build_flow_node_execution_stack(next_node, execution_stack, pending_stack)
        # NEW: AgentExecutor changes — end of extracted C block
    # END NEW: AgentExecutor changes ──────────────────────────────────────────

    def build_flow_node_execution_stack(self, node: Node, execution_stack: List[str], pending_stack: Dict[str, List[str]]):
        
        if node.id not in pending_stack:
            pending_stack[node.id] = []

        for input_port in node.get_input_ports():
            if node.isNetwork():
                down_stream_nodes = self.get_downstream_nodes(input_port)
                for down_node in down_stream_nodes:
                    if (down_node.isDirty()):
                        if down_node.id not in pending_stack:
                            pending_stack[down_node.id] = []
                            # make sure we're not adding duplicates
                            if node.id not in pending_stack[down_node.id]:  
                                pending_stack[down_node.id].append(node.id)


            get_upstream_nodes_list = self.get_upstream_nodes(input_port)
       
            for up_node in get_upstream_nodes_list:
                # Need to be careful here. logic in NodeNetwork was "if up_node.id == self.id: continue".
                # 'self' was the network. 
                # executor doesn't know the network id. 
                # Actually, up_node.network_id should match node.network_id usually.
                # If we encounter the Network Node itself (if it's recursive?), we might skip.
                # Use node.network_id?
                
                 
                if up_node.isDirty() == False:
                    continue
    
                if up_node.isDataNode():
                    if up_node.id not in pending_stack[node.id]:
                        pending_stack[node.id].append(up_node.id)
                    # build data node execution stack
                    self.build_data_node_execution_stack(up_node, execution_stack, pending_stack)
        
                if up_node.isNetwork():
                    if up_node.id not in pending_stack[node.id]:
                        pending_stack[node.id].append(up_node.id)

                    self.build_flow_node_execution_stack(up_node, execution_stack, pending_stack)

    def build_data_node_execution_stack(
        self,
        node: Node,
        execution_stack: List[str],
        pending_stack: Dict[str, List[str]],
        _building: Optional[Set[str]] = None,
    ):
        """Build the pending-stack entries for a data-node subgraph.

        _building is a set of node IDs currently on the DFS recursion stack.
        When a node already in _building is encountered we have detected a
        cycle: the caller has already recorded the dependency so we stop
        recursing rather than looping forever.  The mutual entries in
        pending_stack mean the deadlock guard in cook_flow_control_nodes will
        fire with a clear error instead of a silent hang.
        """
        if _building is None:
            _building = set()

        if node.id not in pending_stack:
            pending_stack[node.id] = []

        # Cycle guard: if we re-enter a node that is already being traversed,
        # stop recursion here.  The caller already added this node's id to its
        # own pending deps before making this call, so the circular dependency
        # is correctly captured in pending_stack for deadlock detection.
        if node.id in _building:
            return
        _building.add(node.id)

        print(" 1. Building data node execution stack for node:", node.name)
        for input_port in node.get_input_data_ports():
            upstream_nodes = self.get_upstream_nodes(input_port)
            for up_node in upstream_nodes:
                # if up_node.id == self.id: continue # removed network check

                # if the node isn't dirty, then skip it.
                if up_node.isDirty() == False:
                    continue
                
                if up_node.isDataNode(): 
                    if up_node.id not in pending_stack[node.id]:
                        pending_stack[node.id].append(up_node.id)
                    
                    self.build_data_node_execution_stack(up_node, execution_stack, pending_stack, _building)

        _building.discard(node.id)

    def propogate_network_inputs_to_internal(self, network_node: Node) -> None:
        assert(network_node.isNetwork()), "propogate_network_inputs() called on non-network node"
         # this is a precompute function for subnetworks
        print("=== PRE-Computing NodeNetwork Subnet:", network_node.name, " with id:", network_node.id)
        # 2. Tunnel Inputs: Propagate Input Data from Subnet Ports to Internal Nodes
        for port_name, port in network_node.inputs.items():
            if port.isDataPort() and port.value is not None:
            #if port.value is not None:
                edges = self.graph.get_outgoing_edges(network_node.id, port_name)
                for edge in edges:
                    target_node = self.graph.get_node_by_id(edge.to_node_id)
                    if target_node:
                        # Push to internal node ports
                        if edge.to_port_name in target_node.inputs:
                            target_node.inputs[edge.to_port_name].setValue(port.value)
                        elif edge.to_port_name in target_node.outputs:
                            target_node.outputs[edge.to_port_name].setValue(port.value)
    
    def propogate_internal_node_outputs_to_network(self, network_node: Node) -> None:
        for port_name, port in network_node.outputs.items():
            edges = self.graph.get_incoming_edges(network_node.id, port_name)
            for edge in edges:
                source_node = self.graph.get_node_by_id(edge.from_node_id)
                if source_node:
                        val = None
                        if edge.from_port_name in source_node.outputs:
                            val = source_node.outputs[edge.from_port_name].value
                        elif edge.from_port_name in source_node.inputs:
                            val = source_node.inputs[edge.from_port_name].value
                        
                        if val is not None:
                            port.value = val
                            port._isDirty = False

    def push_data_from_node(self, node: Node) -> None:
        for port_name, port in node.outputs.items():
            if port.isDataPort() and port.value is not None:
    
                val = port.value
                outgoing_edges = self.graph.get_outgoing_edges(node.id, port_name)
                for edge in outgoing_edges:
                    target_node = self.graph.get_node_by_id(edge.to_node_id)
                    if target_node:
                        if edge.to_port_name in target_node.inputs:
                            target_node.inputs[edge.to_port_name].setValue(val)
                        elif edge.to_port_name in target_node.outputs:
                            target_node.outputs[edge.to_port_name].setValue(val)
                        # ── on_edge_data hook ─────────────────────────────
                        if self.on_edge_data is not None:
                            self.on_edge_data(
                                node.id, port_name, edge.to_node_id, edge.to_port_name
                            )

    # Copied helper methods from NodeNetwork that are needed
    def get_upstream_nodes(self, port) -> List[Node]:
        incoming_edges = self.graph.get_incoming_edges(port.node_id, port.port_name)
        upstream_nodes: List[Node] = []
        for edge in incoming_edges:
            source_node = self.graph.get_node_by_id(edge.from_node_id)
            if source_node:
                upstream_nodes.append(source_node)
        return upstream_nodes
    
    def get_downstream_nodes(self, port) -> List[Node]:
        #assert(False), "get_downstream_nodes is deprecated, use get_upstream_nodes instead and reverse logic in build_flow_node_execution_stack"
        outgoing_edges = self.graph.get_outgoing_edges(port.node_id, port.port_name)
        downstream_nodes: List[Node] = []
        for edge in outgoing_edges:
            dest_node = self.graph.get_node_by_id(edge.to_node_id)
            #print(" @@@@@@@@IS ACTIVATE?", dest_node.inputs[edge.to_port_name].value)
            if dest_node and dest_node not in downstream_nodes:
                downstream_nodes.append(dest_node)
        return downstream_nodes
    

    # TODO: do we really need this?
    async def cook_data_nodes(self, node):
        #assert(False), "cook_data_nodes is deprecated, use cook_flow_control_nodes instead"
        execution_stack = []
        pending_stack = {}
        #execution_stack.append(node.id)    
        #pending_stack[node.id] = []
        

        if node.isDataNode():
            self.build_data_node_execution_stack(node, execution_stack, pending_stack)
        


        print("Pending Stack:", pending_stack)
        print("Initial Execution Stack:", execution_stack)

        # iterate through the pending stack and if the dependencies are all met, 
        # add to execution stack
        # This should be part of the regular cooking loop

        for node_id in list(pending_stack.keys()):
            deps = pending_stack[node_id]
            if len(deps) == 0:
                execution_stack.append(node_id)
                del pending_stack[node_id]
    
        # now iterate through the execution stack and process nodes
        while execution_stack:  
            print("Execution Stack:", execution_stack)
            cur_node_id = execution_stack.pop(0)
            #ur_node = node.network.get_node(cur_node_id)
            cur_node = self.graph.get_node_by_id(cur_node_id)
            if cur_node and cur_node.isDataNode():
                print(".   Cooking node:", cur_node.name, cur_node_id)
                context = ExecutionContext(cur_node).to_dict()
                print(".       Context:", context)
                result = await cur_node.compute(context)
                print(".       Result:", result.command, result.data_outputs)
                
                # now update output ports with the computed values. 
                # the compute function should return a dict of output port names 
                # to values.
                result.deserialize_result(cur_node)

                # Propagate output values to connected downstream input ports
                # (same logic as _execute_single_node via push_data_from_node).
                self.push_data_from_node(cur_node)
            
        
            # TODO:
            # BUG: a node network will currently:
            # 1. process a node twice. Once because compute step does the
            # execution and second because we are doing it here again.
            # 2. not handle flow control nodes properly.
            # We need to separate data node cooking from flow control node cooking.
            # 3. The unit tests currently keep track of nodes cooked externally.
            # but our node network will not add to that stack properly.
            # after processing, update pending stack
            for node_id in list(pending_stack.keys()):
                deps = pending_stack[node_id]
                if cur_node_id in deps:
                    deps.remove(cur_node_id)
                    if len(deps) == 0:
                        execution_stack.append(node_id)
                        del pending_stack[node_id]
