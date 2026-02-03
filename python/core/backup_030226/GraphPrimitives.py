from typing import Tuple, NamedTuple, Any

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
