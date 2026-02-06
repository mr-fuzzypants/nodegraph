from collections import defaultdict
from typing import Optional, List, Dict, Any, Type, Callable, TYPE_CHECKING
#from typing import Dict, List, Optional, Any, TYPE_CHECKING
from .Node import Node, ExecCommand, ExecutionResult, ExecutionContext
from .GraphPrimitives import Edge, Graph, GraphNode
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
    _network_registry: Dict[str, Type['Node']] = {}
    graph: Graph = Graph()  # Shared graph context for all networks

    @classmethod
    def register(cls, type_name: str) -> Callable[[Type['NodeNetwork']], Type['NodeNetwork']]:
        """Decorator to register a node class with a specific type name."""
        def decorator(subclass: Type['NodeNetwork']) -> Type['NodeNetwork']:
            if cls._network_registry.get(type_name):
                raise ValueError(f"NodeNetwork type '{type_name}' is already registered.")
            cls._network_registry[type_name] = subclass
            return subclass
        return decorator

    @classmethod
    def create_network(cls, node_name: str, type_name: str, *args, **kwargs) -> 'Node':
        """Factory method to create a node instance by type name."""
        # Use simple dictionary lookup for O(1) factory
        if type_name not in cls._network_registry:
            # Fallback or strict error? 
            # For now, let's just try to be helpful or error out.
            raise ValueError(f"Unknown node type '{type_name}'")
        

        node_class = cls._network_registry[type_name]
        new_node = node_class(node_name, type_name, *args, **kwargs)

        NodeNetwork.graph.add_node(new_node)
        
        print("!!!!!!!!!!!!! Created NodeNetwork of type:", type_name, " with id:", node_name, new_node.id)
        #assert(False)
        return new_node


    #all_nodes = {}  # type: Dict[str, 'NodeNetwork']
    #all_nodes_by_id = {}  # type: Dict[str, 'NodeNetwork']

    #nodes: Dict[str, Node] = {}  # Dictionary of nodes in the net
    #edges: List[Edge] = [] # Centralized connection storage (Arena Pattern)

    #incoming_edges = defaultdict(list)  # type: Dict[Tuple[str, str], List[Edge]]
    #outgoing_edges = defaultdict(list)  # type: Dict[Tuple[str, str], List[Edge]]
    
    

    def __init__(self, id: str, type, network):
        super().__init__(id, type=type, network=network)
        #self.nodes: Dict[str, Node] = {}  # Dictionary of nodes in the net
        #self.edges: List[Edge] = [] # Centralized connection storage (Arena Pattern)

        self.network = network  # Placeholder

        self.is_flow_control_node = True
        self.is_async_network = False
        #self.is_data_node = False

        # Implement an adjacency map for efficient lookups.
        # Note that we're using a default dict with a composite key. We *may* want to use a 
        # string key instead made up from the id and port name for simplicity.
        # TODO: we have to ensure a node id is unique in a network for this to work properly.
        # TODO: also port names have to be unique per node.
        #self.incoming_edges = defaultdict(list)  # type: Dict[Tuple[str, str], List[Edge]]
        #self.outgoing_edges = defaultdict(list)  # type: Dict[Tuple[str, str], List[Edge]]
    
        #NodeNetwork.graph.add_node(self)
        self.path = f"{self.network.path}/{self.name}" if self.network else self.name
    
    
    def isNetwork(self) -> bool:
        return True

    def isRootNetwork(self) -> bool:
        return self.network is None

    def isSubnetwork(self) -> bool:
        return self.network is not None

    # find a node in all networks by id
    def find_node_by_id(self, uid: str) -> Optional[Node]:
        return NodeNetwork.graph.find_node_by_id(uid)
        return NodeNetwork.all_nodes.get(uid)
    


    def add_node(self, node: Node):
        #if self.find_node(node.id):
        #    raise ValueError(f"Node with id '{node.id}' already exists in the global node registry {NodeNetwork.all_nodes.keys()}")
        #if self.nodes.get(id):
        #    raise ValueError(f"Node with id '{id}' already exists in the network")
       
        
#
        #self.nodes[node.id] = node
        # TODO: why am I not setting the network on the node here?
        # TODO: probably should pass it in as an arg on node create.
        #node.set_network(self) # Inject network context

        #NodeNetwork.all_nodes[node.id] = node
        NodeNetwork.graph.add_node(node)

    
    # TODO: this should be get_node_by_id for clarity
    def get_node_by_id(self, node_id: str) -> Optional[Node]:
        return NodeNetwork.graph.get_node_by_id(node_id)
        if node_id == self.id:
            return self
        return self.nodes.get(node_id)

    # This method looks at nodes LOCAL to this network only
    def get_node_by_name(self, name: str) -> Optional[Node]:
        return NodeNetwork.graph.get_node_by_name(name)
        for node in self.nodes.values():
            if node.name == name:
                return node
        return None
    
    def get_node_by_path(self, path: str) -> Optional[Node]:
        return NodeNetwork.graph.get_node_by_path(path)
        for node in self.nodes.values():
            if node.get_path() == path:
                return node
        return None
    
        
    # --- Edge Management ---
    
    def add_edge(self, from_node_id: str, from_port_name: str, to_node_id: str, to_port_name: str):
        edge = self.graph.add_edge(from_node_id, from_port_name, to_node_id, to_port_name)
        return edge
        # Validation could happen here or in upper layers
        #edge = Edge(from_node_id, from_port_name, to_node_id, to_port_name)
        #self.edges.append(edge)

        self.incoming_edges[(to_node_id, to_port_name)].append(edge)
        self.outgoing_edges[(from_node_id, from_port_name)].append(edge)
        return edge

    def get_incoming_edges(self, node_id: str, port_name: str) -> List[Edge]:
        return self.graph.get_incoming_edges(node_id, port_name)
        # Linear search for now (O(E)). In Rust/Optimized Python, use an Adjacency List (Dict[to, List[Edge]])
        return self.incoming_edges.get((node_id, port_name), [])
        #return [e for e in self.edges if e.to_node_id == node_id and e.to_port_name == port_name]

    def get_outgoing_edges(self, node_id: str, port_name: str) -> List[Edge]:
        return self.graph.get_outgoing_edges(node_id, port_name)
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

    # not currenty being used, but will be needed.
    def can_connect_output_to(self, source_node, from_port_name: str, other_node: 'Node', to_port_name: str) -> bool:
        #assert(False), "CAN CONNECT OUTPUT TO NOT USED ANYMORE"
        from_port = source_node.outputs.get(from_port_name)
        to_port = other_node.inputs.get(to_port_name)

        if not from_port:
            raise ValueError(f"Output port '{from_port_name}' not found in node '{self.id}'")
        if not to_port:
            raise ValueError(f"Input port '{to_port_name}' not found in node '{other_node.id}'")
        
        # Identity check using IDs for portability
        if from_port.node_id == other_node.id:
            return False
        
        return True
    


    def connect_output_to_refactored(self, source_node, from_port_name: str, other_node: 'Node', to_port_name: str):
        #assert(False)
        from_port = source_node.outputs.get(from_port_name)
        to_port = other_node.inputs.get(to_port_name)

        print("CONNECTING NODES:", source_node.name, from_port_name,"->", other_node.name, to_port_name)
        if not to_port:
            if source_node.network_id == other_node.id:
                to_port = other_node.outputs.get(to_port_name)

       
        if not from_port:
            if source_node.id == other_node.network_id:
                from_port = source_node.inputs.get(from_port_name)
            else:
                assert(False), "FROM PORT STILL NOT FOUND"

        if not from_port:
            raise ValueError(f"Output port '{from_port_name}' not found in node '{self.name}'")
        if not to_port:
            raise ValueError(f"Input port '{to_port_name}' not found in node '{other_node.name}'")
        
        if from_port.node_id == other_node.id:
            raise ValueError("Cannot connect a node's output to its own input")
        
        

        existing_connections = self.get_incoming_edges(other_node.id, to_port_name)
        print("  ->Existing Connections on", other_node.name, to_port_name, ":", len(existing_connections))
        if existing_connections:
            if to_port.isInputOutputPort() or from_port.isInputOutputPort():
                #TODO: what is this case?
                # allow multiple connections for input/output ports
                pass
            else:
                raise ValueError(f"Error: Input port '{to_port_name}' on node '{other_node.id}' is already connected")
        
        
        #return from_port.connectTo(to_port)
        edge = self.add_edge(source_node.id, from_port_name, other_node.id, to_port_name)

        existing_connections = self.get_incoming_edges(other_node.id, to_port_name)

        return edge

   


    def connect_node_output_to(self, source_node, from_port_name, other_node, to_port_name):
        #source_node.connect_output_to(from_port_name, other_node, to_port_name)
        return self.connect_output_to_refactored(source_node, from_port_name, other_node, to_port_name)


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
                 start_node = self.get_node_by_id(edge.to_node_id)
                 if start_node:
                     builder.compile_chain(start_node)
        else:
             # If no explicit exec point, we might need a different strategy
             # or simply do nothing (empty subnetwork)
             pass
    

    # TODO: start nodes should be part of the execution context?
    # LEAVE THIS COMMENTED OUT FOR NOW, IT'S A WORK IN PROGRESS. USE IT FOR
    # REFERENCE BUT IT SHOULD NOT be necessary as all of this logic
    # should be handled by the cook_flow_control_nodes method and the execution context.
    async def compute(self, start_nodes: Optional[List[Node]]=None, executionContext: Optional[Any]=None) -> ExecutionResult:
        
        #return ExecutionResult(ExecCommand.CONTINUE)

        #assert(False), "NodeNetwork compute method is a work in progress. Use cook_flow_control_nodes for now."
        """
        Executes the network as a subnet.
        1. Tunnels data from Subnet Inputs to Internal Nodes.
        2. Executes internal nodes starting from 'exec' input or provided start_nodes.
        3. Tunnels data from Internal Nodes to Subnet Outputs.
        """
        
        # 1. Update Inputs from Context (Standard Node Behavior)
        if executionContext:
             ExecutionContext(self).from_dict(executionContext)

        assert(self.isNetwork()), "compute() called on non-network node"
        """"
        # this is a precompute function for subnetworks
        print("=== PRE-Computing NodeNetwork Subnet:", self.name, " with id:", self.id)
        # 2. Tunnel Inputs: Propagate Input Data from Subnet Ports to Internal Nodes
        for port_name, port in self.inputs.items():
            if port.isDataPort() and port.value is not None:
                edges = self.get_outgoing_edges(self.id, port_name)
                for edge in edges:
                    target_node = self.get_node_by_id(edge.to_node_id)
                    print("@@@@ Tunneling input port", port_name, "value", port.value, "to internal node", edge.to_node_id, "port", edge.to_port_name)
                    if target_node:
                        # Push to internal node ports
                        if edge.to_port_name in target_node.inputs:
                            target_node.inputs[edge.to_port_name].value = port.value
                        elif edge.to_port_name in target_node.outputs:
                            # Edge case: pushing to an output (passthrough?)
                            target_node.outputs[edge.to_port_name].value = port.value
        """

        """
        # 3. Determine Internal Start Nodes
        print("======= Building execition lost for Subnet:", self.name, " with id:", self.id)
        internal_start_nodes = []
        if start_nodes:
            internal_start_nodes = start_nodes
        elif "exec" in self.inputs:
            # Automatic start: Find internal nodes connected to the 'exec' input
            edges = self.get_outgoing_edges(self.id, "exec")
            for edge in edges:
                node = self.get_node_by_id(edge.to_node_id)
                if node:
                    internal_start_nodes.append(node)
        print("--- Internal start nodes for subnet:", [n.name for n in internal_start_nodes])
        
        # 4. Execute Internal Graph
        # Use simple serial execution for the start nodes for now

        for node in internal_start_nodes:
            print("")
            print(">>>.        Cooking internal subnet node:", node.name, " in subnet:", self.name)
            await self.cook_flow_control_nodes(node)
            print("")

        """
        print("=== POST-Computing NodeNetwork Subnet:", self.name, " with id:", self.id)
        # 5. Tunnel Outputs: Populates Subnet Outputs from Internal Nodes
        
        """
        for port_name, port in self.outputs.items():
            if port.isDataPort():
                # Look for edges coming INTO the subnet output from INSIDE
                # Connection direction: InternalNode.Out -> Subnet.Out (as Input to Subnet Node from inside)
                edges = self.get_incoming_edges(self.id, port_name)
                for edge in edges:
                    source_node = self.get_node_by_id(edge.from_node_id)
                    if source_node:
                         val = None
                         if edge.from_port_name in source_node.outputs:
                             val = source_node.outputs[edge.from_port_name].value
                         elif edge.from_port_name in source_node.inputs:
                             val = source_node.inputs[edge.from_port_name].value
                         
                         if val is not None:
                             port.value = val
        """
        # 6. Return Result
        control_outputs = {}
        if "finished" in self.outputs:
             control_outputs["finished"] = True
    
        

        return ExecutionResult(ExecCommand.CONTINUE, control_outputs=control_outputs)


    @classmethod
    def createRootNetwork(cls, name: str, type:str) -> 'NodeNetwork':
        #return NodeNetwork(id=name, network=None)

        network = NodeNetwork.create_network(name, type, network=None)
        print("####Created Root Network node with id:", network.id)
        return network
    
    def createNetwork(self, name: str, type:str="NodeNetworkSystem") -> 'NodeNetwork':

        #network_path = self.get_path()
        network_path = self.graph.get_path(self.id)  # Get the path of the current network node
        node_path = f"{network_path}/{name}"

        print("Creating sub-network:", name, "in network:", self.name, " of path:", node_path)

        #if self.get_node_by_name(name):
        if self.get_node_by_path(node_path):
            raise ValueError(f"Node with id '{id}' already exists in the network")
       

        network = NodeNetwork.create_network(name, type, self)
        #network = NodeNetwork(id=name, network=self)
       
        #self.add_node(network)

        print(".  ####Added Network node to parent network:", self.name, " with id:", network.id)
    

        return network


    #def create_node(self, id: str, type: str, *args, **kwargs) -> Node:
    #    # Alias helper for createNode (standard python convention)
    #    return self.createNode(id, type, *args, **kwargs)

    def createNode(self, name: str, type: str,*args, **kwargs) -> Node:

        #network_path = self.get_path()
        network_path = self.graph.get_path(self.id)  # Get the path of the current network node
        node_path = f"{network_path}:{name}"

        

        #if self.get_node_by_name(name):
        if self.get_node_by_path(node_path):
            raise ValueError(f"Node with id '{name}' already exists in the network")
        
        print("Creating node:", name, "of type:", type, "in network:", self.name, " of path:", node_path)
        # Backwards compatibility/specific logic for legacy calls
        # If args is present, assume value is passed positionally
        if type == "Parameter" and "value" not in kwargs and not args:
            kwargs["value"] = 0

        # Inject owner for Arena/Hierarchy awareness
        #if "owner" not in kwargs:
        #    kwargs["owner"] = self

        # Delegate to Node Factory
        try:
            node = Node.create_node(name, type, network=self, *args, **kwargs)
        except ValueError as e:
            # Re-raise with context if needed, or let it bubble
            raise ValueError(f"Error creating node '{type}': {e}")

        #node = Node(id, type, owner=self)
        self.add_node(node)
        return node
    
    

    def connectNodesByPath(self, from_node_path: str, from_port_name: str, to_node_path: str, to_port_name: str) -> Edge:
        from_node = self.get_node_by_path(from_node_path)
        to_node = self.get_node_by_path(to_node_path)

        if not from_node:
            raise ValueError(f"Source node with id '{from_node_path}' does not exist in the network")
        if not to_node:
            raise ValueError(f"Target node with id '{to_node_path}' does not exist in the network '{self.name}'")
        
        # New Logic: Delegate to NodePort, but we know it adds to 'self.edges'
        # Verification happens in connectTo
        #from_node.connect_output_to(from_port_name, to_node, to_port_name) 
        self.connect_node_output_to(from_node, from_port_name, to_node, to_port_name)
        
        # We can reconstruct the Edge object that was implicitly created
        edge = Edge(from_node.id, from_port_name, to_node.id, to_port_name)
        return edge

    def connectNodes(self, from_node_name: str, from_port_name: str, to_node_name: str, to_port_name: str) -> Edge:
        

        print("Connecting nodes by name:", from_node_name, from_port_name, to_node_name, to_port_name)
        
        #from_node = self.get_node_by_name(from_node_name)
        #to_node = self.get_node_by_name(to_node_name)

        #network_path = self.get_path()
        network_path = self.graph.get_path(self.id)  # Get the path of the current network node
        from_node_path = f"{network_path}:{from_node_name}"
        to_node_path = f"{network_path}:{to_node_name}"
        

        from_node = self.get_node_by_path(from_node_path)
        to_node = self.get_node_by_path(to_node_path)

        # TODO: we need to search with global scope if not found locally
        if from_node_name == self.name:
            from_node = self
        if to_node_name == self.name:
            to_node = self


        if not from_node:
            raise ValueError(f"Source node with id '{from_node_name}' does not exist in the network")
        if not to_node:
            raise ValueError(f"Target node with id '{to_node_name}' does not exist in the network '{self.name}'")
        

        #print("  From Node:", from_node.name, from_node.network.id, self.id)

        # if my node is inside a network, then we connect
        # the output to the network output port instead.
        #if from_node.network.id == self.id:
        #    assert(False), "from_node found inside local network. "

        #if not from_node:
        #    raise ValueError(f"Source node with id '{from_node_name}' does not exist in the network")
        #if not to_node:
        #    raise ValueError(f"Target node with id '{to_node_name}' does not exist in the network '{self.name}'")
        
        

        #if from_node.id == to_node.id:
        #    raise ValueError("Cannot connect a node to itself")
        
        #from_node_id = self.get_node_by_name(from_node_name).id
        #to_node_id = self.get_node_by_name(to_node_name).id
        #from_node = self.get_node(from_node_id)
        #to_node = self.get_node(to_node_id)

        # New Logic: Delegate to NodePort, but we know it adds to 'self.edges'
        # Verification happens in connectTo
        #from_node.connect_output_to(from_port_name, to_node, to_port_name) 
        self.connect_node_output_to(from_node, from_port_name, to_node, to_port_name)
        
        # We can reconstruct the Edge object that was implicitly created
        edge = Edge(from_node.id, from_port_name, to_node.id, to_port_name)
        return edge
    
    def deleteNode(self, name: str):

        print(" ---- Deleting node with name:", name, "from network:", self.name, self.id, self.isNetwork())
        print(".   -- networkId:", self.id)

        for graph_node in NodeNetwork.graph.nodes.values():
            print(".   -- Graph Node:", graph_node.name, graph_node.id, " in network:", graph_node.network_id)  

        network_path = self.graph.get_path(self.id)
        #network_path = self.get_path()
        node_path = f"{network_path}:{name}"
        
        node = self.get_node_by_path(node_path)

        if not node:
            raise ValueError(f"Node with id '{name}' does not exist in the network")
        
        id  = node.id
        # Arena Pattern: Cleanup connections associated with this node
        #self.edges = [e for e in self.edges if e.from_node_id != id and e.to_node_id != id]

        # TODO: deleting a node involves removing all connections to/from it first
        # This cleanup is critical in Rust/TS to prevent orphaned pointers
        #del self.nodes[id]

        NodeNetwork.graph.deleteNode(id)

    @classmethod
    def deleteAllNodes(cls):
        #cls.nodes.clear()
        #cls.edges.clear()

        #cls.all_nodes.clear()
        #cls.all_nodes_by_id.clear()
        #cls.incoming_edges.clear()
        #cls.outgoing_edges.clear()

        NodeNetwork.graph.reset()


    """"""
    # get all the downstream ports connected to src_port. By default we don't
    # include I/O ports in the results, and just return the "final" downstream ports.
    #
    # TODO: revist if we make this function iterative instead of recursive.
    # TODO: for now though it's more readable.
    def get_downstream_ports(self, src_port: NodePort, include_io_ports: bool=False) -> List[NodePort]:
        #assert(False), "get_downstream_ports is deprecated, use port.get_downstream_ports instead"
        #assert(False), "get_downstream_ports is deprecated, use port.get_downstream_ports instead"
        downstream_ports = []
        outgoing_edges = self.get_outgoing_edges(src_port.node.id, src_port.port_name)

        for edge in outgoing_edges:
            dest_node = self.get_node_by_id(edge.to_node_id)
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
            src_node = self.get_node_by_id(edge.from_node_id)
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
                #port_node = self.get_node_by_id(port.node_id)

                #upstream_ports = port.node.network.get_upstream_ports(port, include_io_ports=True)
                upstream_ports = self.get_upstream_ports(port, include_io_ports=True)
                
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
        #incoming_edges = port.node.network.get_incoming_edges(port.node.id, port.port_name)
        incoming_edges = self.get_incoming_edges(port.node.id, port.port_name)
        
        for edge in incoming_edges:
            #src_node = port.node.network.get_node_by_id(edge.from_node_id)
            src_node = self.get_node_by_id(edge.from_node_id)
            if src_node and src_node not in upstream_nodes:
                upstream_nodes.append(src_node)
        
        return upstream_nodes

    def get_downstream_nodes(self, port: NodePort) -> List[Node]:
        downstream_nodes = []
        #outgoing_edges = port.node.network.get_outgoing_edges(port.node.id, port.port_name)
        outgoing_edges = self.get_outgoing_edges(port.node.id, port.port_name)

        for edge in outgoing_edges:
            #dest_node = port.node.network.get_node_by_id(edge.to_node_id)
            dest_node = self.get_node_by_id(edge.to_node_id)
            if dest_node and dest_node not in downstream_nodes:
                downstream_nodes.append(dest_node)
        
        return downstream_nodes



    def build_flow_node_execution_stack(self, node: Node, execution_stack: List[str], pending_stack: Dict[str, List[str]]):
        
        if node.id not in pending_stack:
            pending_stack[node.id] = []

        # why are we looking for data ports?
        #for input_port in node.get_input_data_ports():
        for input_port in node.get_input_ports():
            if node.isNetwork():
                down_stream_nodes = self.get_downstream_nodes(input_port)
                for down_node in down_stream_nodes:
                    if (down_node.isDirty()):
                        if down_node.id not in pending_stack:
                            pending_stack[down_node.id] = []
                            # make sure we're not adding duplicates
                            # TODO: maybe use a set instead of a list?
                            if node.id not in pending_stack[down_node.id]:  
                                pending_stack[down_node.id].append(node.id)


            get_upstream_nodes_list = self.get_upstream_nodes(input_port)
       
            for up_node in get_upstream_nodes_list:
            
                if up_node.id == self.id:
                    continue

                if up_node.isDirty() == False:
                    continue
    
                #if up_node.isDirty():
                    #assert(False), "Upstream node of flow control node is dirty. This should not happen because we should have already checked for this in build_data_node_execution_stack. Upstream node: " + up_node.name + " of type " + up_node.type
                #assert(False), "Upstream node of flow control node is not a data node. Upstream node: " + up_node.name + " of type " + up_node.type
                if up_node.isDataNode():
                    #assert(False), "Data nodes should be handled in build_data_node_execution_stack, not build_flow_node_execution_stack"
                    
                    if up_node.id not in pending_stack[node.id]:
                        pending_stack[node.id].append(up_node.id)
                    # build data node execution stack
                    self.build_data_node_execution_stack(up_node, execution_stack, pending_stack)
        
                if up_node.isNetwork():
                    if up_node.id not in pending_stack[node.id]:
                        pending_stack[node.id].append(up_node.id)

                    self.build_flow_node_execution_stack(up_node, execution_stack, pending_stack)
                    
    # do I even need this function separate from build_flow_node_execution_stack? I don't thinkg
    # so. I can probably remove this.
    def build_data_node_execution_stack(self, node: Node, execution_stack: List[str], pending_stack: Dict[str, List[str]]):
        
        if node.id not in pending_stack:
            pending_stack[node.id] = []
        print(" 1. Building data node execution stack for node:", node.name)
        for input_port in node.get_input_data_ports():
            upstream_nodes = self.get_upstream_nodes(input_port)
            for up_node in upstream_nodes:
                if up_node.id == self.id:
                    continue

                # if the node isn't dirty, then skip it.
                if up_node.isDirty() == False:
                    continue
                
                if up_node.isDataNode(): 
                    if up_node.id not in pending_stack[node.id]:
                        pending_stack[node.id].append(up_node.id)
                    
                    self.build_data_node_execution_stack(up_node, execution_stack, pending_stack)

    def build_network_execution_stack(self, node: Node, execution_stack: List[str], pending_stack: Dict[str, List[str]]):
        pass


    def propogate_network_inputs_to_internal(self, network_node: 'NodeNetwork') -> None:
        assert(network_node.isNetwork()), "propogate_network_inputs() called on non-network node"
         # this is a precompute function for subnetworks
        print("=== PRE-Computing NodeNetwork Subnet:", self.name, " with id:", self.id)
        # 2. Tunnel Inputs: Propagate Input Data from Subnet Ports to Internal Nodes
        for port_name, port in network_node.inputs.items():
            if port.isDataPort() and port.value is not None:
                edges = self.get_outgoing_edges(network_node.id, port_name)
                for edge in edges:
                    target_node = self.get_node_by_id(edge.to_node_id)
                    if target_node:
                        # Push to internal node ports
                        if edge.to_port_name in target_node.inputs:
                            target_node.inputs[edge.to_port_name].value = port.value
                        elif edge.to_port_name in target_node.outputs:
                            # Edge case: pushing to an output (passthrough?)
                            target_node.outputs[edge.to_port_name].value = port.value
    
    def propogate_internal_node_outputs_to_network(self, network_node: Node) -> None:
        #assert(False), "propogate_internal_node_outputs_to_network not fully implemented yet. Need to determine which internal nodes are connected to the network outputs and in what order to propogate values. For now, this function is not called."
        for port_name, port in network_node.outputs.items():
            #TODO: double check logic here. do we need to check if it's a data port?
            #if port.isDataPort(): 
            # Look for edges coming INTO the subnet output from INSIDE
            # Connection direction: InternalNode.Out -> Subnet.Out (as Input to Subnet Node from inside)
            edges = self.get_incoming_edges(network_node.id, port_name)
            for edge in edges:
                source_node = self.get_node_by_id(edge.from_node_id)
                if source_node:
                        val = None
                        if edge.from_port_name in source_node.outputs:
                            val = source_node.outputs[edge.from_port_name].value
                        elif edge.from_port_name in source_node.inputs:
                            val = source_node.inputs[edge.from_port_name].value
                        
                        if val is not None:
                            port.value = val


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
            #node_short_id = cur_node_id.split('/')[-1]
            #cur_node = self.get_node(node_short_id)
            cur_node = self.find_node_by_id(cur_node_id) 
                 # Fallback for cross-network references or full paths
            #     cur_node = NodeNetwork.all_nodes.get(cur_node_id)
           
            assert(cur_node), f"Node '{cur_node_id}' not found in network {node.network.path} during flow control cooking"

            if cur_node: 
                if cur_node.isNetwork():
                    # for subnetworks, we need to propogate the network inputs first
                    self.propogate_network_inputs_to_internal(cur_node)

                print("")
                print(".   Cooking node:", cur_node.name, cur_node_id)
                print("")
                context = ExecutionContext(cur_node).to_dict()

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
                            target_node = self.get_node_by_id(edge.to_node_id)
                            if target_node:
                                if edge.to_port_name in target_node.inputs:
                                    target_node.inputs[edge.to_port_name].value = val
                                elif edge.to_port_name in target_node.outputs:
                                    target_node.outputs[edge.to_port_name].value = val
                # ---------------------------
               
                if cur_node.isNetwork():
                    # for subnetworks, we need to propogate the internal outputs back to the network outputs
                    self.propogate_internal_node_outputs_to_network(cur_node)


                connected_ids = []
                for control_name, control_value in result.control_outputs.items():
                    edges = self.get_outgoing_edges(cur_node.id, control_name)
                    next_ids = [e.to_node_id for e in edges if e.to_node_id != self.id]
                    connected_ids.extend(next_ids)

        

                # Update Pending Stack with next control flow nodes
                for next_node_id in connected_ids:
                    next_node = self.get_node_by_id(next_node_id)
                    if next_node:
                        self.build_flow_node_execution_stack(next_node, execution_stack, pending_stack)
                    
                    else:
                        AssertionError(f"Next node '{next_node_id}' not found in network during flow control cooking")

            for node_id in list(pending_stack.keys()):
                deps = pending_stack[node_id]
                if cur_node_id in deps:
                    if len(deps) != len(set(deps)):
                        assert(False), f"Duplicate dependencies found in pending stack for node '{node_id}'. Dependencies: {deps}"
    
                    deps.remove(cur_node_id)
                if len(deps) == 0:
                    if node_id != cur_node_id:
                        execution_stack.append(node_id)
                    del pending_stack[node_id]

        for node_id in pending_stack.keys():
            node = self.get_node_by_id(node_id)
            node_name = node.name if node else "Unknown"
        
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
            cur_node = self.get_node_by_id(cur_node_id)
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

    
@NodeNetwork.register("NodeNetworkSystem")
class NodeNetworkSystem(NodeNetwork):
    def __init__(self, id, type="NodeNetworkSystem", network=None, **kwargs):
        super().__init__(id, type=type, network=network)
        #self.type = "NodeNetworkRoot"
        self.is_flow_control_node = True
        self.cooking_internally = False
        self._isDirty = True

    async def compute(self, executionContext: Optional[Any]=None) -> ExecutionResult:
        # Root network compute can be a no-op or can handle global execution context setup if needed.
        print(">>> Computing Root NodeNetworkSystem:", self.name, " with id:", self.id)
        return ExecutionResult(ExecCommand.CONTINUE)
    

@NodeNetwork.register("FlowNodeNetwork")
class FlowNodeNetwork(NodeNetwork):
    def __init__(self, id, type="FlowNodeNetwork", network=None, **kwargs):
        super().__init__(id, type=type, network=network)
        #self.type = "NodeNetworkRoot"
        self.is_flow_control_node = True
        self._isDirty = True

        self.add_control_input("exec")
        self.add_control_output("finished")


    async def compute(self, executionContext: Optional[Any]=None) -> ExecutionResult:
        
        if executionContext:
             ExecutionContext(self).from_dict(executionContext)

        control_outputs = {}
        if "finished" in self.outputs:
             control_outputs["finished"] = True
    
        result = ExecutionResult(ExecCommand.CONTINUE)
        result.control_outputs = control_outputs    

        
    


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
    

