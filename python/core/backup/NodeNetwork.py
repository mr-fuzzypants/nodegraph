

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from .Node import Node, ExecCommand, ExecutionResult
from .NodePort import (
    InputOutputDataPort, 
    InputOutputControlPort, 
    NodePort, 
    Connection,
    PortDirection, 
    PortFunction
)

if TYPE_CHECKING:
    pass


from logging import getLogger
logger = getLogger(__name__)
class NodeNetwork(Node):
    def __init__(self, id: str, owner: Optional['NodeNetwork']=None):
        super().__init__(id, type="NodeNetwork", owner=owner)
        self.nodes: Dict[str, Node] = {}  # Dictionary of nodes in the net
        self.connections: List[Connection] = [] # Centralized connection storage (Arena Pattern)

        # self.owner = owner  # Placeholder

        self.is_flow_control_node = True
        self.is_async_network = False
        #self.is_data_node = False
    
    def isNetwork(self) -> bool:
        return True

    def isRootNetwork(self) -> bool:
        return self.owner is None

    def isSubnetwork(self) -> bool:
        return self.owner is not None

    def add_node(self, node: Node):
        self.nodes[node.id] = node
    
    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

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
        print(" ++++ Adding control input port to network:", port_name)
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
            for pname, port in self.outputs.items(): # Debug
                print("  Available output port:", pname)
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

        if to_port.incoming_connections:
            if to_port.direction == PortDirection.INPUT_OUTPUT or from_port.direction == PortDirection.INPUT_OUTPUT:
                #TODO: what is this case?
                # allow multiple connections for input/output ports
                pass
            else:
                raise ValueError(f"Error: Input port '{to_port_name}' on node '{other_node.id}' is already connected")
        

        from_port.connectTo(to_port)



    async def compute_step(self, start_nodes: Optional[List[Node]]=None) -> Optional[List[Node]]:
        # If start_nodes is provided, only compute from those nodes):
        # This is the Core "Runner" Loop. 
        # In TS/Rust, this would be the Event Loop or Task Scheduler.
        import asyncio

        if start_nodes:
            compute_nodes = start_nodes
            explicit_next_nodes = []
            has_explicit_results = False

            # Run nodes in parallel
            tasks = [cur_node.compute() for cur_node in compute_nodes]
            results = await asyncio.gather(*tasks)

            for result in results:
                # New "Runner" logic using ExecutionResult
                # The Node tells us what to do, we don't assume recursion.
                if result and isinstance(result, ExecutionResult):
                    has_explicit_results = True
                    if result.command == ExecCommand.CONTINUE:
                        if result.next_nodes:
                            explicit_next_nodes.extend(result.next_nodes)
                        elif result.next_node_ids:
                             # Resolve IDs to Nodes (Arena Lookup)
                             for nid in result.next_node_ids:
                                 node = self.get_node(nid)
                                 if node: explicit_next_nodes.append(node)
                                 else: logger.error(f"ExecutionResult returned unknown node id: {nid}")

                    elif result.command == ExecCommand.LOOP_AGAIN:
                         # Use synchronous loop handling in LoopNode for now.
                         pass
            
            if has_explicit_results:
                return explicit_next_nodes

            # Fallback: Legacy Port Scanning
            next_nodes = []
            for cur_node in compute_nodes:           
                # find next nodes to compute based on control flow
                # print("Finding next nodes to compute...")
                for output_port in cur_node.get_output_control_ports():
                    # print("Output control port:", output_port.port_name)
                    for connection in output_port.outgoing_connections:
                        # print("  connection to node:", connection.to_port.node.id, connection.to_port.isActive() )
                        if connection.to_port.isActive():
                            # next_node = connection.to_port.node
                            #if not next_node.is_loop_node:
                            next_nodes.append(connection.to_port.node)

            return next_nodes
        return None



    # override
    def get_inputoutput_control_ports(self) -> List[NodePort]:
        # Using new Enums
        return [port for port in self.inputs.values() 
                if port.direction == PortDirection.INPUT_OUTPUT and port.function == PortFunction.CONTROL]

    async def compute(self, start_nodes: Optional[List[Node]]=None):
        # if it's a network then we need to find the start nodes connected to the exec input.
        # for now though we have to find out why the basic case doesn't work.
        #if not start_nodes:
        #    start_nodes = [self]

        self.precompute()
        next_nodes = start_nodes

        if next_nodes is None:
            control_ports = self.get_inputoutput_control_ports()
            next_nodes = []
            for port in control_ports:
                for connection in port.outgoing_connections:
                    if connection.to_port.isActive():
                        next_nodes.append(connection.to_port.node)
                        logger.info(f"  Found start node from network exec port: {connection.to_port.node.id}")
                    else:
                        logger.info(f"  Exec port connection not active: {connection.to_port.node.id}")

        while True:
            next_nodes = await self.compute_step(next_nodes)
            if not next_nodes:
                break
            # Logic loop safety break could be added here

        self.markClean()
        self.postcompute()


    def compile(self, builder: Any):
        """
        Supports 'Tunneling' during compilation.
        Also acts as the 'Control Flow' entry point if this Network is in a chain.
        """
        # 1. Resolve Data Tunnels
        for port_name, port in self.inputs.items():
            src_port = port.get_source()
            if src_port:
                var_src = builder.get_var(src_port)
                builder.set_var(port, var_src)

        # 2. Compile Internal Control Flow
        # If the network receives control, we must dive inside and compile the nodes driven by our inputs.
        control_ports = self.get_inputoutput_control_ports()
        for port in control_ports:
             nodes_to_compile = [conn.to_node for conn in port.outgoing_connections]
             for node in nodes_to_compile:
                 # Recurse down into the network logic
                 builder.compile_chain(node)

    def createNetwork(self, id: str) -> 'NodeNetwork':
        if self.nodes.get(id):
            raise ValueError(f"Node with id '{id}' already exists in the network")
        network = NodeNetwork(id=id, owner=self)
        self.add_node(network)

        return network

    def createNode(self, id: str, type: str, **kwargs) -> Node:

        if self.nodes.get(id):
            raise ValueError(f"Node with id '{id}' already exists in the network")
        
        # Backwards compatibility/specific logic for legacy calls
        if type == "Parameter" and "value" not in kwargs:
            kwargs["value"] = 0

        # Inject owner for Arena/Hierarchy awareness
        if "owner" not in kwargs:
            kwargs["owner"] = self

        # Delegate to Node Factory
        try:
            node = Node.create_node(id, type, **kwargs)
        except ValueError as e:
            # Re-raise with context if needed, or let it bubble
            raise ValueError(f"Error creating node '{type}': {e}")

        #node = Node(id, type, owner=self)
        self.add_node(node)
        return node

    def connectNodes(self, from_node_id: str, from_port_name: str, to_node_id: str, to_port_name: str) -> Connection:
        from_node = self.get_node(from_node_id)
        to_node = self.get_node(to_node_id)

        if not from_node:
            raise ValueError(f"Source node with id '{from_node_id}' does not exist in the network")
        if not to_node:
            raise ValueError(f"Target node with id '{to_node_id}' does not exist in the network")
        
        connection = from_node.connect_output_to(from_port_name, to_node, to_port_name) # type: ignore (Implicit connection return from Node)
        
        # Arena Pattern: Track connection centrally
        if connection:
            self.connections.append(connection)

        return connection
    
    def deleteNode(self, id: str):
        if not self.nodes.get(id):
            raise ValueError(f"Node with id '{id}' does not exist in the network")
        
        # Arena Pattern: Cleanup connections associated with this node
        self.connections = [c for c in self.connections if c.from_node_id != id and c.to_node_id != id]

        # TODO: deleting a node involves removing all connections to/from it first
        # This cleanup is critical in Rust/TS to prevent orphaned pointers
        del self.nodes[id]

    

