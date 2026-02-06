from typing import Tuple, NamedTuple, Dict, List, Optional
#from typing import Optional, List, Dict, Any, Type, Callable, TYPE_CHECKING
from collections import  defaultdict

import uuid

# Defining Edge as a simple data structure
# Using NamedTuple for immutability and simple hashability if needed later
class Edge(NamedTuple):
    from_node_id: str
    from_port_name: str
    to_node_id: str
    to_port_name: str
    
    # Optional metadata for debug or visualization, but core logic should rely on first 4 fields
    edge_type: str = "default" # "data", "control"

    def __repr__(self):
        return f"Edge({self.from_node_id}.{self.from_port_name} -> {self.to_node_id}.{self.to_port_name})"


# Base class for Nodes. Will be subclassed by actual node implementations. 
# Contains common properties and methods required for graph traversal.
class GraphNode:
    def __init__(self, 
                 name: str, 
                 type: str, 
                 network_id: str = None
                    ):
        self.name = name
        self.id = uuid.uuid4().hex
        self.uuid = uuid.uuid4().hex  # Unique identifier for the node instance
        self.network_id = network_id

    def __repr__(self):
        return f"GraphNode({self.id})" 

class Graph:
    #all_nodes = {}  # type: Dict[str, 'GraphNode']
    #all_nodes_by_id = {}  # type: Dict[str, 'GraphNode']

    nodes: Dict[str, GraphNode] = {}  # Dictionary of nodes in the net
    edges: List[Edge] = [] # Centralized connection storage (Arena Pattern)

    incoming_edges = defaultdict(list)  # type: Dict[Tuple[str, str], List[Edge]]
    outgoing_edges = defaultdict(list)  # type: Dict[Tuple[str, str], List[Edge]]

    def __init__(self):
        pass
    
     # find a node in all networks by id
    def find_node_by_id(self, uid: str) -> Optional[GraphNode]:
        return self.nodes.get(uid)
    

    def add_edge(self, from_node_id: str, from_port_name: str, to_node_id: str, to_port_name: str):
        # Validation could happen here or in upper layers
        edge = Edge(from_node_id, from_port_name, to_node_id, to_port_name)
        self.edges.append(edge)

        self.incoming_edges[(to_node_id, to_port_name)].append(edge)
        self.outgoing_edges[(from_node_id, from_port_name)].append(edge)
        return edge

    def get_incoming_edges(self, node_id: str, port_name: str) -> List[Edge]:
        return self.incoming_edges.get((node_id, port_name), [])
       
    def get_outgoing_edges(self, node_id: str, port_name: str) -> List[Edge]:
        return self.outgoing_edges.get((node_id, port_name), [])
        


    def add_node(self, node: GraphNode):
        #if self.find_node(node.id):
        #    raise ValueError(f"Node with id '{node.id}' already exists in the global node registry {NodeNetwork.all_nodes.keys()}")
        if self.nodes.get(node.id):
            raise ValueError(f"Node with id '{node.name}' already exists in the network")
       
        

        self.nodes[node.id] = node
        # TODO: why am I not setting the network on the node here?
        # TODO: probably should pass it in as an arg on node create.
        #node.set_network(self) # Inject network context

        print(f"### Graph: Adding node {node.name} to global registry", node.network_id)
        self.nodes[node.id] = node

    
    # TODO: this should be get_node_by_id for clarity
    def get_node_by_id(self, node_id: str) -> Optional[str]:
        return self.nodes.get(node_id)

    # This method looks at nodes LOCAL to this network only
    def get_node_by_name(self, name: str) -> Optional[str]:
        for node in self.nodes.values():
            if node.name == name:
                return node
        return None
    
    def get_node_by_path(self, path: str) -> Optional[GraphNode]:
        #return NodeNetwork.graph.get_node_by_path(path)
        for node in self.nodes.values():
            if node.get_path() == path:
                return node
        return None
    
    def getNode(self, node_id: str) -> Optional[GraphNode]:
        return self.get_node_by_id(node_id)

     # convenience method to get the network node object from the network id
    def getNetwork(self, network_id: Optional[str] = None) -> 'Graph':
        network = self.get_node_by_id(network_id)
        if not network:
            return None
        #assert(network is not None), f"Network with ID '{network_id}' not found"
        assert(network.isNetwork()), f"Node with ID '{network_id}' is not a Network"   
        return network

    # build up the path from a givent node id
    def get_path(self, node_id) -> str:
        
        node = self.get_node_by_id(node_id)
        assert(node is not None), f"Node with ID '{node_id}' not found"

        path_elements = []
        #cur_parent =self.network
        cur_parent = self.getNetwork(node.network_id)
        while cur_parent:
            path_elements.append(cur_parent.name)
            #cur_parent = cur_parent.network
            cur_parent = self.getNetwork(cur_parent.network_id) 
        
        path_elements.reverse()
        full_path = "/" + "/".join(path_elements)
        if node.isNetwork():
            full_path += f"/{node.name}"
        else:
            full_path += f":{node.name}"

        # TODO: fix this hack please.
        if full_path.startswith("//"):
            full_path = full_path[1:]   
        return full_path
    

    def deleteNode(self, name: str):
    
        
        node = self.get_node_by_id(name)
        if not node:
            raise ValueError(f"Node with id '{name}' does not exist in the network")
        

        id  = node.id
        # Arena Pattern: Cleanup connections associated with this node
        self.edges = [e for e in self.edges if e.from_node_id != id and e.to_node_id != id]

        # TODO: deleting a node involves removing all connections to/from it first
        # This cleanup is critical in Rust/TS to prevent orphaned pointers
        del self.nodes[id]
    
    def reset(self):
        self.nodes.clear()
        self.edges.clear()
        self.incoming_edges.clear()
        self.outgoing_edges.clear()
    