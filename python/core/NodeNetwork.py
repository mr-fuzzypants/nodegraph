from collections import defaultdict
import asyncio
from typing import Optional, List, Dict, Any, Type, Callable, TYPE_CHECKING, Tuple
#from typing import Dict, List, Optional, Any, TYPE_CHECKING
from .Node import Node
from .GraphPrimitives import Edge, Graph, GraphNode
from .NodePort import (
    InputOutputDataPort, 
    InputOutputControlPort, 
    NodePort, 
    # Connection, # REMOVED: Replaced by Edge
    PortDirection, 
    PortFunction
)
from .Types import NodeKind

from .Interface import INodePort, INodeNetwork, IExecutionResult, IExecutionContext
if TYPE_CHECKING:
    pass


from logging import getLogger
logger = getLogger(__name__)

from .Executor import ExecCommand, ExecutionResult, ExecutionContext   




class NodeNetwork(Node):
    _network_registry: Dict[str, Type['Node']] = {}
    # graph: Graph = Graph()  # Shared graph context for all networks (REMOVED: Instance based)

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

        if hasattr(new_node, 'graph') and new_node.graph:
             new_node.graph.add_node(new_node)
        
        print("!!!!!!!!!!!!! Created NodeNetwork of type:", type_name, " with id:", node_name, new_node.id)
        #assert(False)
        return new_node


    def __init__(self, id: str, type, network_id, graph: Optional[Graph] = None):
        super().__init__(id, type=type, network_id=network_id)
        #self.nodes: Dict[str, Node] = {}  # Dictionary of nodes in the net
        #self.edges: List[Edge] = [] # Centralized connection storage (Arena Pattern)
        
        self.kind = NodeKind.NETWORK
        self.graph = graph

        self.network_id = network_id  # Placeholder

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
        self.path = "UNSet"

        
    


    def isRootNetwork(self) -> bool:
        return self.network_id is None

    def isSubnetwork(self) -> bool:
        return self.network_id is not None

    # find a node in all networks by id
    def find_node_by_id(self, uid: str) -> Optional[Node]:
        assert(False), "NodeNetwork.find_node_by_id should not be called directly. Use graph.find_node_by_id instead to ensure global node registry access."
        return self.graph.find_node_by_id(uid)
    
    
    # TODO: this should be get_node_by_id for clarity
    def get_node_by_id(self, node_id: str) -> Optional[Node]:
        assert(False), "NodeNetwork.get_node_by_id should not be called directly. Use graph.get_node_by_id instead to ensure global node registry access."
        return self.graph.get_node_by_id(node_id)

    # This method looks at nodes LOCAL to this network only
    def get_node_by_name(self, name: str) -> Optional[Node]:
        assert(False), "NodeNetwork.get_node_by_name should not be called directly. Use graph.get_node_by_name instead to ensure global node registry access."
        return self.graph.get_node_by_name(name)
        
    
    def get_node_by_path(self, path: str) -> Optional[Node]:
        assert(False), "NodeNetwork.get_node_by_path should not be called directly. Use graph.get_node_by_path instead to ensure global node registry access."
        return self.graph.get_node_by_path(path)
       
    
        
    # --- Edge Management ---
    
    def add_edge(self, from_node_id: str, from_port_name: str, to_node_id: str, to_port_name: str) -> Edge:
        assert(False), "NodeNetwork.add_edge should not be called directly. Use graph.add_edge instead to ensure global edge management."
        edge = self.graph.add_edge(from_node_id, from_port_name, to_node_id, to_port_name)
        return edge
        # Validation could happen here or in upper layers
        #edge = Edge(from_node_id, from_port_name, to_node_id, to_port_name)
        #self.edges.append(edge)

        self.incoming_edges[(to_node_id, to_port_name)].append(edge)
        self.outgoing_edges[(from_node_id, from_port_name)].append(edge)
        return edge

    def get_incoming_edges(self, node_id: str, port_name: str) -> List[Edge]:
        assert(False), "NodeNetwork.get_incoming_edges should not be called directly. Use graph.get_incoming_edges instead to ensure global edge management."
        return self.graph.get_incoming_edges(node_id, port_name)
        # Linear search for now (O(E)). In Rust/Optimized Python, use an Adjacency List (Dict[to, List[Edge]])
        return self.incoming_edges.get((node_id, port_name), [])
        #return [e for e in self.edges if e.to_node_id == node_id and e.to_port_name == port_name]

    def get_outgoing_edges(self, node_id: str, port_name: str) -> List[Edge]:
        assert(False), "NodeNetwork.get_outgoing_edges should not be called directly. Use graph.get_outgoing_edges instead to ensure global edge management."
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
         
        port = InputOutputControlPort(self.id, port_name)
        self.inputs[port_name] = port
        return port


    def add_data_input_port(self, port_name: str) -> InputOutputDataPort:
        if port_name in self.inputs:
            raise ValueError(f"Data input port '{port_name}' already exists in node '{self.id}'")
        
        port = InputOutputDataPort(self.id, port_name)
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
        
        

        existing_connections = self.graph.get_incoming_edges(other_node.id, to_port_name)
        print("  ->Existing Connections on", other_node.name, to_port_name, ":", len(existing_connections))
        if existing_connections:
            if to_port.isInputOutputPort() or from_port.isInputOutputPort():
                #TODO: what is this case?
                # allow multiple connections for input/output ports
                pass
            else:
                raise ValueError(f"Error: Input port '{to_port_name}' on node '{other_node.id}' is already connected")
        
        
        #return from_port.connectTo(to_port)
        edge = self.graph.add_edge(source_node.id, from_port_name, other_node.id, to_port_name)

        existing_connections = self.graph.get_incoming_edges(other_node.id, to_port_name)

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
        
        if from_port.node_id == other_node.id:
            raise ValueError("Cannot connect a node's output to its own input")

        # assert(from_port.isInputOutputPort()), "Source port must be an input/output port"
        assert(from_port.direction == PortDirection.INPUT_OUTPUT), "Source port must be an input/output port"

        # Check existing connections (Tunneling supports 1:1 typically, or 1:N?)
        # For now, simplistic check
        existing = self.graph.get_outgoing_edges(self.id, from_port_name) 
        # Wait, Tunneling is inside? 
        # If 'self' is the node, outgoing edges are stored in 'self.edges' 
        # where from_node_id == self.id.
        
        # NOTE: Tunnel connections are stored in the Network's edge list 
        # just like any other connection.
        
        #TODO: fix this.
        #if to_port.node.network != self and to_port.node != self:
             # Standard check that both are in this network?
        #     pass 

        # Create Edge directly to avoid "Not attached to network" error
        # since 'self' (the network) is the node, and it manages its own edges.
        # FIX: Always use port_name for consistency in Edge lookup
        self.graph.add_edge(self.id, from_port.port_name, other_node.id, to_port.port_name)

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
             edges = self.graph.get_outgoing_edges(self.id, 'exec')
             for edge in edges:
                 start_node = self.graph.get_node_by_id(edge.to_node_id)
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
        
        # 6. Return Result
        control_outputs = {}
        if "finished" in self.outputs:
             control_outputs["finished"] = True
    
        

        return ExecutionResult(ExecCommand.CONTINUE, control_outputs=control_outputs)


    @classmethod
    def createRootNetwork(cls, name: str, type:str) -> 'NodeNetwork':
        
        # Create a new graph context for this root network
        graph = Graph()
        network = NodeNetwork.create_network(name, type, network_id=None, graph=graph)
        print("####Created Root Network node with id:", network.id)
        return network
    
    def createNetwork(self, name: str, type:str="NodeNetworkSystem") -> 'NodeNetwork':

        network_path = self.graph.get_path(self.id)  # Get the path of the current network node
        node_path = f"{network_path}/{name}"

        print("Creating sub-network:", name, "in network:", self.name, " of path:", node_path)

        if self.graph.get_node_by_path(node_path):
            raise ValueError(f"Node with id '{name}' already exists in the network")
       

        network = NodeNetwork.create_network(name, type, network_id=self.id, graph=self.graph)
      
        print(".  ####Added Network node to parent network:", self.name, " with id:", network.id)
    

        return network


    def createNode(self, name: str, type: str,*args, **kwargs) -> Node:

        network_path = self.graph.get_path(self.id)  # Get the path of the current network node
        node_path = f"{network_path}:{name}"

        if self.graph.get_node_by_path(node_path):
            raise ValueError(f"Node with id '{name}' already exists in the network")
        
        print("Creating node:", name, "of type:", type, "in network:", self.name, " of path:", node_path)
        # Backwards compatibility/specific logic for legacy calls
        # If args is present, assume value is passed positionally
        if type == "Parameter" and "value" not in kwargs and not args:
            kwargs["value"] = 0

        # Delegate to Node Factory
        try:
            node = Node.create_node(name, type, network_id=self.id, *args, **kwargs)
        except ValueError as e:
            # Re-raise with context if needed, or let it bubble
            raise ValueError(f"Error creating node '{type}': {e}")

        self.graph.add_node(node)
        node.graph = self.graph
        return node
    
    

    def connectNodesByPath(self, from_node_path: str, from_port_name: str, to_node_path: str, to_port_name: str) -> Edge:
        from_node = self.graph.get_node_by_path(from_node_path)
        to_node = self.graph.get_node_by_path(to_node_path)

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

        network_path = self.graph.get_path(self.id)  # Get the path of the current network node
        from_node_path = f"{network_path}:{from_node_name}"
        to_node_path = f"{network_path}:{to_node_name}"
        

        from_node = self.graph.get_node_by_path(from_node_path)
        to_node = self.graph.get_node_by_path(to_node_path)

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

        for graph_node in self.graph.nodes.values():
            print(".   -- Graph Node:", graph_node.name, graph_node.id, " in network:", graph_node.network_id)  

        network_path = self.graph.get_path(self.id)
        node_path = f"{network_path}:{name}"
        
        node = self.graph.get_node_by_path(node_path)

        if not node:
            raise ValueError(f"Node with id '{name}' does not exist in the network")
        
        id  = node.id
        # Arena Pattern: Cleanup connections associated with this node
        #self.edges = [e for e in self.edges if e.from_node_id != id and e.to_node_id != id]

        # TODO: deleting a node involves removing all connections to/from it first
        # This cleanup is critical in Rust/TS to prevent orphaned pointers
        #del self.nodes[id]

        self.graph.deleteNode(id)

    @classmethod
    def deleteAllNodes(cls):
        #cls.nodes.clear()
        #cls.edges.clear()

        #cls.all_nodes.clear()
        #cls.all_nodes_by_id.clear()
        #cls.incoming_edges.clear()
        #cls.outgoing_edges.clear()

        pass # Global graph is removed. Tests should instantiate new graphs.


    """"""
    # get all the downstream ports connected to src_port. By default we don't
    # include I/O ports in the results, and just return the "final" downstream ports.
    #
    # TODO: revist if we make this function iterative instead of recursive.
    # TODO: for now though it's more readable.
    def get_downstream_ports(self, src_port: NodePort, include_io_ports: bool=False) -> List[NodePort]:
        #assert(False), "get_downstream_ports is deprecated, use port.get_downstream_ports instead"
        #assert(False), "get_downstream_ports is deprecated, use port.get_downstream_ports instead"
        
        return self.graph.get_downstream_ports(src_port, include_io_ports=include_io_ports)
        downstream_ports = []
        outgoing_edges = self.graph.get_outgoing_edges(src_port.node_id, src_port.port_name)

        for edge in outgoing_edges:
            dest_node = self.graph.get_node_by_id(edge.to_node_id)
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

    # NOTE: used by get_input_port_value to look upstream for the source of truth for a port's value. This is necessary because of tunneling through I/O ports, where the value may actually be coming from further upstream than the immediate connection.
    def get_upstream_ports(self, port: NodePort, include_io_ports: bool=False) -> List[NodePort]:
        return self.graph.get_upstream_ports(port, include_io_ports=include_io_ports)
        #assert(False), "get_upstream_ports is deprecated, use port.get_upstream_ports instead"
        upstream_ports = []
        incoming_edges = self.graph.get_incoming_edges(port.node_id, port.port_name)

        for edge in incoming_edges:
            src_node = self.graph.get_node_by_id(edge.from_node_id)
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
                upstream_ports = self.graph.get_upstream_ports(port, include_io_ports=True)
                
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
        return self.graph.get_upstream_nodes(port)
    
        upstream_nodes = []
        #incoming_edges = port.node.network.get_incoming_edges(port.node.id, port.port_name)
        incoming_edges = self.get_incoming_edges(port.node_id, port.port_name)
        
        for edge in incoming_edges:
            #src_node = port.node.network.get_node_by_id(edge.from_node_id)
            src_node = self.get_node_by_id(edge.from_node_id)
            if src_node and src_node not in upstream_nodes:
                upstream_nodes.append(src_node)
        
        return upstream_nodes

    def get_downstream_nodes(self, port: NodePort) -> List[Node]:
        return self.graph.get_downstream_nodes(port)
        downstream_nodes = []
        #outgoing_edges = port.node.network.get_outgoing_edges(port.node.id, port.port_name)
        outgoing_edges = self.get_outgoing_edges(port.node_id, port.port_name)

        for edge in outgoing_edges:
            #dest_node = port.node.network.get_node_by_id(edge.to_node_id)
            dest_node = self.get_node_by_id(edge.to_node_id)
            if dest_node and dest_node not in downstream_nodes:
                downstream_nodes.append(dest_node)
        
        return downstream_nodes





    
@NodeNetwork.register("NodeNetworkSystem")
class NodeNetworkSystem(NodeNetwork):
    def __init__(self, id, type="NodeNetworkSystem", network_id=None, graph=None, **kwargs):
        super().__init__(id, type=type, network_id=network_id, graph=graph)
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
    def __init__(self, id, type="FlowNodeNetwork", network_id=None, graph=None, **kwargs):
        super().__init__(id, type=type, network_id=network_id, graph=graph)
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

        
    



