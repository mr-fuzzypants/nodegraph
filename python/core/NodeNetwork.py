from collections import defaultdict

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from .Node import Node, ExecCommand, ExecutionResult, ExecutionContext
from .GraphPrimitives import Edge
from .NodePort import (
    InputOutputDataPort, 
    InputOutputControlPort, 
    NodePort, 
    # Connection, # REMOVED: Replaced by Edge
    PortDirection, 
    PortFunction
)

if TYPE_CHECKING:
    pass


from logging import getLogger
logger = getLogger(__name__)
class NodeNetwork(Node):

    all_nodes = {}  # type: Dict[str, 'NodeNetwork']

    def __init__(self, id: str, network):
        super().__init__(id, type="NodeNetwork", network=network)
        self.nodes: Dict[str, Node] = {}  # Dictionary of nodes in the net
        self.edges: List[Edge] = [] # Centralized connection storage (Arena Pattern)

        self.network = network  # Placeholder

        self.is_flow_control_node = True
        self.is_async_network = False
        #self.is_data_node = False

        # Implement an adjacency map for efficient lookups.
        # Note that we're using a default dict with a composite key. We *may* want to use a 
        # string key instead made up from the id and port name for simplicity.
        # TODO: we have to ensure a node id is unique in a network for this to work properly.
        # TODO: also port names have to be unique per node.
        self.incoming_edges = defaultdict(list)  # type: Dict[Tuple[str, str], List[Edge]]
        self.outgoing_edges = defaultdict(list)  # type: Dict[Tuple[str, str], List[Edge]]
    
        self.path = f"{self.network.path}/{self.id}" if self.network else self.id
    def isNetwork(self) -> bool:
        return True

    def isRootNetwork(self) -> bool:
        return self.network is None

    def isSubnetwork(self) -> bool:
        return self.network is not None

    # find a node in all networks by id
    def find_node(self, uid: str) -> Optional[Node]:
        return NodeNetwork.all_nodes.get(uid)
    
    @classmethod
    def id_to_node(cls, id: str) -> Optional[Node]:
        return cls.all_nodes.get(id)

    def add_node(self, node: Node):
        #if self.find_node(node.id):
        #    raise ValueError(f"Node with id '{node.id}' already exists in the global node registry {NodeNetwork.all_nodes.keys()}")
        if self.nodes.get(id):
            raise ValueError(f"Node with id '{id}' already exists in the network")
       
        

        self.nodes[node.id] = node
        # TODO: why am I not setting the network on the node here?
        # TODO: probably should pass it in as an arg on node create.
        node.set_network(self) # Inject network context

        NodeNetwork.all_nodes[node.get_path()] = node
    
    def get_node(self, node_id: str) -> Optional[Node]:
        if node_id == self.id:
            return self
        return self.nodes.get(node_id)
        
    # --- Edge Management ---
    
    def add_edge(self, from_node_id: str, from_port_name: str, to_node_id: str, to_port_name: str):
        # Validation could happen here or in upper layers
        edge = Edge(from_node_id, from_port_name, to_node_id, to_port_name)
        self.edges.append(edge)

        self.incoming_edges[(to_node_id, to_port_name)].append(edge)
        self.outgoing_edges[(from_node_id, from_port_name)].append(edge)
        return edge

    def get_incoming_edges(self, node_id: str, port_name: str) -> List[Edge]:
        # Linear search for now (O(E)). In Rust/Optimized Python, use an Adjacency List (Dict[to, List[Edge]])
        return self.incoming_edges.get((node_id, port_name), [])
        #return [e for e in self.edges if e.to_node_id == node_id and e.to_port_name == port_name]

    def get_outgoing_edges(self, node_id: str, port_name: str) -> List[Edge]:
        return self.outgoing_edges.get((node_id, port_name), [])
        #return [e for e in self.edges if e.from_node_id == node_id and e.from_port_name == port_name]
    
    # -----------------------

    """
    I want to eventually support async networks, but for now this is just a placeholder.
    Aysnc networks would allow nodes to run in parallel, with proper handling of data dependencies.
    Synchronous networks run nodes in a single thread, can be compiled to webassembly more easily,
    and are simpler to reason about. For now contents of a network are always run synchronously.
    """
    def isAsyncNetwork(self) -> bool:
        # Placeholder for future async network support
        return False
    

    # a node netword has onlt i/o ports that are input/output ports. 
    # These are "passthrough" ports that connect to internal nodes.
    def add_control_input_port(self, port_name: str) -> InputOutputControlPort:
        if port_name in self.inputs:
            raise ValueError(f"Control input port '{port_name}' already exists in node '{self.id}'")
         
        port = InputOutputControlPort(self, port_name)
        self.inputs[port_name] = port
        return port


    def add_data_input_port(self, port_name: str) -> InputOutputDataPort:
        if port_name in self.inputs:
            raise ValueError(f"Data input port '{port_name}' already exists in node '{self.id}'")
        
        port = InputOutputDataPort(self, port_name)
        self.inputs[port_name] = port

        return port

    # Refactored for cleaner logic / explicit 'self' usage / type hints
    def connect_to_network_output(self, from_node: Node, from_port_name: str, to_port_name: str):
        from_port = from_node.outputs.get(from_port_name)
        to_port = self.outputs.get(to_port_name)

        if not from_port:
            raise ValueError(f"Output port '{from_port_name}' not found in node '{from_node.id}'")
       
        if not to_port:
             raise ValueError(f"Network Output port '{to_port_name}' not found in network '{self.id}'")
        
        if from_port.node.id == from_node.id and self.id == from_node.id: # Identity check needs careful thought in networks
             raise ValueError("Cannot connect a node's output to its own input")
        
        # Using new Enums
        # assert(from_port.isOutputPort() or from_port.isInputOutputPort())
        assert(from_port.direction == PortDirection.OUTPUT or from_port.direction == PortDirection.INPUT_OUTPUT), "Source port must be an input/output port"
        
        if to_port.incoming_connections:
            # Replaced complex port logic with Enum checks
            if to_port.direction == PortDirection.INPUT_OUTPUT or from_port.direction == PortDirection.INPUT_OUTPUT:
                #TODO: what is this case?
                # allow multiple connections for input/output ports
                pass
            else:
                 raise ValueError(f"Error: Port '{to_port_name}' on network '{self.id}' is already connected")
        

        from_port.connectTo(to_port)
    
    def connect_network_input_to(self, from_port_name: str, other_node: Node, to_port_name: str):
        from_port = self.inputs.get(from_port_name)
        to_port = other_node.inputs.get(to_port_name)

    
        if not from_port:
            raise ValueError(f"Network Input port '{from_port_name}' not found in network '{self.id}'")
        if not to_port:
            raise ValueError(f"Input port '{to_port_name}' not found in node '{other_node.id}'")
        
        if from_port.node.id == other_node.id:
            raise ValueError("Cannot connect a node's output to its own input")

        # assert(from_port.isInputOutputPort()), "Source port must be an input/output port"
        assert(from_port.direction == PortDirection.INPUT_OUTPUT), "Source port must be an input/output port"

        # Check existing connections (Tunneling supports 1:1 typically, or 1:N?)
        # For now, simplistic check
        existing = self.get_outgoing_edges(self.id, from_port_name) 
        # Wait, Tunneling is inside? 
        # If 'self' is the node, outgoing edges are stored in 'self.edges' 
        # where from_node_id == self.id.
        
        # NOTE: Tunnel connections are stored in the Network's edge list 
        # just like any other connection.
        
        if to_port.node.network != self and to_port.node != self:
             # Standard check that both are in this network?
             pass 

        # Create Edge directly to avoid "Not attached to network" error
        # since 'self' (the network) is the node, and it manages its own edges.
        # FIX: Always use port_name for consistency in Edge lookup
        self.add_edge(self.id, from_port.port_name, other_node.id, to_port.port_name)

        # Trigger update?
        # from_port.connectTo(to_port) # Skipped


    def compile(self, builder: Any):
        """
        Compiles the network content by resolution data tunnels and following the 'exec' input port.
        """
        
        # 1. Resolve Data Tunnels (Forward external inputs to internal placeholders)
        for port_name, port in self.inputs.items():
            # If the Network Input port is connected on the OUTSIDE, get the variable
            src_port = port.get_source()
            if src_port:
                var_src = builder.get_var(src_port)
                # Map the Network's Input Port object (which acts as a Source internally)
                # to that same variable.
                builder.set_var(port, var_src)

        # 2. Follow the standard 'exec' entry point
        if 'exec' in self.inputs:
             # Find internal nodes connected to this input
             # Input ports on a Network act as Sources for internal nodes.
             # The connections are stored in the Network's edge list as:
             # From: self.id, Port: 'exec' -> To: InternalNode, Port: Input
             edges = self.get_outgoing_edges(self.id, 'exec')
             for edge in edges:
                 start_node = self.get_node(edge.to_node_id)
                 if start_node:
                     builder.compile_chain(start_node)
        else:
             # If no explicit exec point, we might need a different strategy
             # or simply do nothing (empty subnetwork)
             pass
    

    # TODO: start nodes should be part of the execution context?
    async def compute(self, start_nodes: Optional[List[Node]]=None, executionContext: Optional[Any]=None) -> None:
        # if it's a network then we need to find the start nodes connected to the exec input.
        # for now though we have to find out why the basic case doesn't work.
        #if not start_nodes:
        #    start_nodes = [self]

        self.precompute()
        next_nodes = start_nodes

        context = ExecutionContext(self).to_dict()
        if context:
            ExecutionContext(self).from_dict(context)

            #assert(False), "Cannot provide both executionContext and have NodeNetwork build one"

        self.markClean()
        self.postcompute()

        # TODO: return some result? We're just retur
        #return ExecutionResult(ExecCommand.CONTINUE, next_nodes)
        return ExecutionResult(ExecCommand.CONTINUE, [])




    def createNetwork(self, id: str) -> 'NodeNetwork':
        if self.nodes.get(id):
            raise ValueError(f"Node with id '{id}' already exists in the network")
        network = NodeNetwork(id=id, network=self)
       
        self.add_node(network)

        return network


    #def create_node(self, id: str, type: str, *args, **kwargs) -> Node:
    #    # Alias helper for createNode (standard python convention)
    #    return self.createNode(id, type, *args, **kwargs)

    def createNode(self, id: str, type: str,*args, **kwargs) -> Node:

        if self.nodes.get(id):
            raise ValueError(f"Node with id '{id}' already exists in the network")
        
        # Backwards compatibility/specific logic for legacy calls
        # If args is present, assume value is passed positionally
        if type == "Parameter" and "value" not in kwargs and not args:
            kwargs["value"] = 0

        # Inject owner for Arena/Hierarchy awareness
        #if "owner" not in kwargs:
        #    kwargs["owner"] = self

        # Delegate to Node Factory
        try:
            node = Node.create_node(id, type, network=self, *args, **kwargs)
        except ValueError as e:
            # Re-raise with context if needed, or let it bubble
            raise ValueError(f"Error creating node '{type}': {e}")

        #node = Node(id, type, owner=self)
        self.add_node(node)
        return node

    def connectNodes(self, from_node_id: str, from_port_name: str, to_node_id: str, to_port_name: str) -> Edge:
        from_node = self.get_node(from_node_id)
        to_node = self.get_node(to_node_id)

        if not from_node:
            raise ValueError(f"Source node with id '{from_node_id}' does not exist in the network")
        if not to_node:
            raise ValueError(f"Target node with id '{to_node_id}' does not exist in the network")
        
        # New Logic: Delegate to NodePort, but we know it adds to 'self.edges'
        # Verification happens in connectTo
        from_node.connect_output_to(from_port_name, to_node, to_port_name) 
        
        # We can reconstruct the Edge object that was implicitly created
        edge = Edge(from_node_id, from_port_name, to_node_id, to_port_name)
        return edge
    
    def deleteNode(self, id: str):
        if not self.nodes.get(id):
            raise ValueError(f"Node with id '{id}' does not exist in the network")
        
        # Arena Pattern: Cleanup connections associated with this node
        self.edges = [e for e in self.edges if e.from_node_id != id and e.to_node_id != id]

        # TODO: deleting a node involves removing all connections to/from it first
        # This cleanup is critical in Rust/TS to prevent orphaned pointers
        del self.nodes[id]

    """"""
    # get all the downstream ports connected to src_port. By default we don't
    # include I/O ports in the results, and just return the "final" downstream ports.
    #
    # TODO: revist if we make this function iterative instead of recursive.
    # TODO: for now though it's more readable.
    def get_downstream_ports(self, src_port: NodePort, include_io_ports: bool=False) -> List[NodePort]:
        #assert(False), "get_downstream_ports is deprecated, use port.get_downstream_ports instead"
        downstream_ports = []
        outgoing_edges = self.get_outgoing_edges(src_port.node.id, src_port.port_name)

        for edge in outgoing_edges:
            dest_node = self.get_node(edge.to_node_id)
            # see if I'm connected to an input port or an output port
            # first see if it's an input port and if not look for output port.
            # this is because I/O ports can be in either inputs or outputs.
            dest_port = dest_node.inputs.get(edge.to_port_name)
            if not dest_port:
                dest_port = dest_node.outputs.get(edge.to_port_name)
            
            if not dest_port:
                continue
        
            # handle tunneling through I/O ports. 
            if dest_port.isInputOutputPort():
                if include_io_ports:
                    downstream_ports.append(dest_port)
                downstream_ports.extend(self.get_downstream_ports(dest_port, include_io_ports=include_io_ports))
            else:
                downstream_ports.append(dest_port)
            
        return downstream_ports

    def get_upstream_ports(self, port: NodePort, include_io_ports: bool=False) -> List[NodePort]:
        #assert(False), "get_upstream_ports is deprecated, use port.get_upstream_ports instead"
        upstream_ports = []
        incoming_edges = self.get_incoming_edges(port.node.id, port.port_name)

        for edge in incoming_edges:
            src_node = self.get_node(edge.from_node_id)
            src_port = src_node.outputs.get(edge.from_port_name)
            if not src_port:
                src_port = src_node.inputs.get(edge.from_port_name)

            if not src_port:
                continue

            # handle tunneling through I/O ports. 
            if src_port.isInputOutputPort():
                if include_io_ports:
                    upstream_ports.append(src_port)
                upstream_ports.extend(self.get_upstream_ports(src_port))
            else:
                upstream_ports.append(src_port)
            
        return upstream_ports
    
    # For an input port, get its value by looking upstream. Once the value is found,
    # propagate that value to all upstream ports from the source to mark them clean.
    def get_input_port_value(self, port: NodePort) -> Any:
        if port._isDirty:
            if port.isInputPort() or port.isInputOutputPort():
                upstream_ports = port.node.network.get_upstream_ports(port, include_io_ports=True)
                
                if upstream_ports:
                    source_value_port = upstream_ports.pop()
                    value = source_value_port.value
                    # for the remaining ports, propogate the value dirty state
                    for up_port in upstream_ports:
                        up_port._dirty = False
                        up_port.value = value
                    port.value = value
                    port._isDirty = False
                    
        return port.value
    

    def get_upstream_nodes(self, port: NodePort) -> List[Node]:
        upstream_nodes = []
        incoming_edges = port.node.network.get_incoming_edges(port.node.id, port.port_name)

        for edge in incoming_edges:
            src_node = port.node.network.get_node(edge.from_node_id)
            if src_node and src_node not in upstream_nodes:
                upstream_nodes.append(src_node)
        
        return upstream_nodes

    def get_downstream_nodes(port: NodePort) -> List[Node]:
        downstream_nodes = []
        outgoing_edges = port.node.network.get_outgoing_edges(port.node.id, port.port_name)

        for edge in outgoing_edges:
            dest_node = port.node.network.get_node(edge.to_node_id)
            if dest_node and dest_node not in downstream_nodes:
                downstream_nodes.append(dest_node)
        
        return downstream_nodes


    def build_flow_node_execution_stack(self, node: Node, execution_stack: List[str], pending_stack: Dict[str, List[str]]):
        
        if node.get_path() not in pending_stack:
            pending_stack[node.get_path()] = []

        for input_port in node.get_input_data_ports():
            get_upstream_nodes_list = self.get_upstream_nodes(input_port)
            for up_node in get_upstream_nodes_list:
                if up_node.isDirty() == False:
                    continue
    
    
                if up_node.isDataNode():
                    pending_stack[node.get_path()].append(up_node.get_path())
                    # build data node execution stack
                    self.build_data_node_execution_stack(up_node, execution_stack, pending_stack)
        
                if up_node.isNetwork():
                    pending_stack[node.get_path()].append(up_node.get_path())
                    self.build_flow_node_execution_stack(up_node, execution_stack, pending_stack)
                    

    # do I even need this function separate from build_flow_node_execution_stack? I don't thinkg
    # so. I can probably remove this.
    def build_data_node_execution_stack(self, node: Node, execution_stack: List[str], pending_stack: Dict[str, List[str]]):
        
        if node.get_path() not in pending_stack:
            pending_stack[node.get_path()] = []

        for input_port in node.get_input_data_ports():
            upstream_nodes = self.get_upstream_nodes(input_port)
            #pending_stack[node.id].extend([up_node.id for up_node in upstream_nodes if up_node.isDataNode()])   
            for up_node in upstream_nodes:
                if up_node.isDirty() == False:
                    continue
                
                if up_node.isDataNode(): 
                    pending_stack[node.get_path()].append(up_node.get_path())
                    self.build_data_node_execution_stack(up_node, execution_stack, pending_stack)


    async def cook_flow_control_nodes(self, node: Node, execution_stack: List[str]=None, pending_stack: Dict[str, List[str]]=None )-> None:

        # Copied from test/test_node_cooking_flow.py (NodeNetworkFixes)
        # Fixes: BFS execution, Robust Data Push, Scoped Node Lookup

        if execution_stack is None:
            execution_stack = []
        if pending_stack is None:
            pending_stack = {}
    
        if node.isFlowControlNode():
            self.build_flow_node_execution_stack(node, execution_stack, pending_stack)
            
        for node_id in list(pending_stack.keys()):
            deps = pending_stack[node_id]
            if len(deps) == 0:
                execution_stack.append(node_id)
                del pending_stack[node_id]
        


        while execution_stack:
            # FIX: Use BFS for safer execution order
            cur_node_id = execution_stack.pop(0)
          

            # FIX: Use self.get_node to ensure we look in THIS network (scoped lookup)
            # Logic adapted from NodeNetworkFixes
            node_short_id = cur_node_id.split('/')[-1]
            cur_node = self.get_node(node_short_id)
            if not cur_node or cur_node.get_path() != cur_node_id:
                 # Fallback for cross-network references or full paths
                 cur_node = NodeNetwork.all_nodes.get(cur_node_id)
           
            assert(cur_node), f"Node '{cur_node_id}' not found in network {node.network.path} during flow control cooking"

            if cur_node: 
                print(".   Cooking node:", cur_node_id)
                context = ExecutionContext(cur_node).to_dict()
                # I don't think you need this... commenting out for now. The context
                # builder should do the right thing
                #context["network_id"] = cur_node.network.id if cur_node.network else None
                #context["node_id"] = cur_node.id
                #context["node_path"] = cur_node.get_path()
                #context["uuid"] = cur_node.uuid
                # print(".       Context:", context)

                result = await cur_node.compute(executionContext=context)

                # given a result object, deserialize the outputs back to the 
                # node's output ports.
                result.deserialize_result(cur_node)

                 # --- NEW PUSH DATA LOGIC (ROBUST) ---
                for port_name, port in cur_node.outputs.items():
                    if port.isDataPort() and port.value is not None:
                        val = port.value
                        outgoing_edges = self.get_outgoing_edges(cur_node.id, port_name)
                        for edge in outgoing_edges:
                            target_node = self.get_node(edge.to_node_id)
                            if target_node:
                                if edge.to_port_name in target_node.inputs:
                                    target_node.inputs[edge.to_port_name].value = val
                                elif edge.to_port_name in target_node.outputs:
                                    target_node.outputs[edge.to_port_name].value = val
                # ---------------------------
               
                connected_ids = []
                for control_name, control_value in result.control_outputs.items():
                    edges = self.get_outgoing_edges(cur_node.id, control_name)
                    next_ids = [e.to_node_id for e in edges]
                    connected_ids.extend(next_ids)

                # Update Pending Stack with next control flow nodes
                for next_node_id in connected_ids:
                    next_node = self.get_node(next_node_id)
                    if not next_node: 
                         # Try global lookup if local fails
                         next_node = NodeNetwork.all_nodes.get(next_node_id) 

                    if next_node:
                        self.build_flow_node_execution_stack(next_node, execution_stack, pending_stack)
                    else:
                        AssertionError(f"Next node '{next_node_id}' not found in network during flow control cooking")

            # print("Processing pending stack after cooking node:", cur_node_id)
            # after processing, update pending stack
            for node_id in list(pending_stack.keys()):
                deps = pending_stack[node_id]
                if cur_node_id in deps:
                    deps.remove(cur_node_id)
                if len(deps) == 0:
                    if node_id != cur_node_id:
                        execution_stack.append(node_id)
                    del pending_stack[node_id]

        assert(len(pending_stack) == 0), "Pending stack should be empty after cooking all flow control nodes"
        #assert(False), "Debug Stop Here"



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
            cur_node = NodeNetwork.all_nodes.get(cur_node_id)
            if cur_node and cur_node.isDataNode():
                print(".   Cooking node:", cur_node_id)
                context = ExecutionContext(cur_node).to_dict()
                print(".       Context:", context)
                result = await cur_node.compute(context)
                print(".       Result:", result.command, result.data_outputs)
                
                # now update output ports with the computed values. 
                # the compute function should return a dict of output port names 
                # to values.
                result.deserialize_result(cur_node)
            
        
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

    

  