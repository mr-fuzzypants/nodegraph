import asyncio
from typing import Optional, List, Dict, Any, Type, Callable, TYPE_CHECKING, Tuple
from enum import Enum, auto
from logging import getLogger

from .Node import Node
from .GraphPrimitives import Graph, Edge
from .Types import PortDirection, PortFunction, NodeKind
from .Interface import IExecutionContext, IExecutionResult

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
            # If the main stack is empty (Body finished), load the loop nodes back in.
            if not execution_stack and deferred_stack:
                # print("--- Batch Completed. Starting Deferred Nodes (Next Iteration) ---")
                # Reverse to maintain stack order if needed, but usually we just want to run them.
                execution_stack.extend(deferred_stack)
                deferred_stack.clear()

            # 2. Parallel Batch Collection
            # Pop EVERYTHING currently in the stack. 
            # Since dependencies are already resolved by 'pending_stack', 
            # all nodes in 'execution_stack' are theoretically ready to run.
            batch_ids = execution_stack[:] 
            execution_stack.clear()
            
            # 3. Parallel Execution
            if not batch_ids: continue

            # Create coroutines for all nodes in the batch
            tasks = [self._execute_single_node(nid) for nid in batch_ids]
            
            # Run them all at the same time and wait for results
            results = await asyncio.gather(*tasks)

            # 4. Result Processing (Sequential update of graph state)
            for (cur_node, result) in results:
                if not cur_node or not result: continue

                # A. Handle Loop Backs (Deferred)
                # Use name check to avoid Enum identity issues with module reloading/path issues in tests
                if result.command.name == "LOOP_AGAIN":
                     deferred_stack.append(cur_node.id)

                # B. Handle Standard Flow (Immediate)
                connected_ids = []
                for control_name, control_value in result.control_outputs.items():
                    print("     [3] Control Output from node", cur_node.name, ":", control_name, "=", control_value)
                    edges = self.graph.get_outgoing_edges(cur_node.id, control_name)
                    # TODO: need to propagate control output values as well I think.
                    for edge in edges:
                        to_node = self.graph.get_node_by_id(edge.to_node_id)
                        if to_node:
                            if to_node.inputs.get(edge.to_port_name):
                                to_node.inputs[edge.to_port_name].setValue(control_value)
                            elif to_node.outputs.get(edge.to_port_name):
                                to_node.outputs[edge.to_port_name].setValue(control_value)


                    next_ids = [e.to_node_id for e in edges if e.to_node_id != cur_node.network_id] # Assuming self.id was network_id? No, NodeNetwork logic was self.id. Here we don't know who called us. 
                    # Wait, logic in NodeNetwork was: if e.to_node_id != self.id. 
                    # The network excludes itself from the next_ids?
                    # If this is running ON a network, 'self' is the network.
                    # We need to know who the network is. Use cur_node.network_id?
                    
                    connected_ids.extend(next_ids)

                # C. Dependency Resolution for Next Nodes
                for next_node_id in connected_ids:
                    next_node = self.graph.get_node_by_id(next_node_id)
                    if next_node:
                        self.build_flow_node_execution_stack(next_node, execution_stack, pending_stack)
            
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

        for node_id in pending_stack.keys():
            node = self.graph.get_node_by_id(node_id)
            node_name = node.name if node else "Unknown"
            print(f"Node '{node_name}' ({node_id}) still has dependencies: {pending_stack[node_id]}")
        
        assert(len(pending_stack) == 0), "Pending stack should be empty after cooking all flow control nodes"

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
        context = ExecutionContext(cur_node).to_dict()
        result = await cur_node.compute(executionContext=context)
        
        # Apply side effects immediately? 
        # In strictly parallel systems we might buffer this, but here
        # we assume python's GIL/single-threaded async protects atomic port writes.
        result.deserialize_result(cur_node)
        
        if cur_node.isNetwork():
            self.propogate_internal_node_outputs_to_network(cur_node)

        self.push_data_from_node(cur_node)
            
        return (cur_node, result)

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

    def build_data_node_execution_stack(self, node: Node, execution_stack: List[str], pending_stack: Dict[str, List[str]]):
        
        if node.id not in pending_stack:
            pending_stack[node.id] = []
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
                    
                    self.build_data_node_execution_stack(up_node, execution_stack, pending_stack)

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
        outgoing_edges = self.graph.get_outgoing_edges(port.node_id, port.port_name)
        downstream_nodes: List[Node] = []
        for edge in outgoing_edges:
            dest_node = self.graph.get_node_by_id(edge.to_node_id)
            if dest_node and dest_node not in downstream_nodes:
                downstream_nodes.append(dest_node)
        return downstream_nodes
