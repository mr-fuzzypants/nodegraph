from typing import Any, List, Dict, Set, Tuple, Optional

class IRBuilder:
    """
    A Builder Class that generates Linear Intermediate Representation (IR) 
    from a Node Graph by traversing it via the `compile` methods of the nodes.
    
    It handles:
    1. Variable Allocation (Temp registers)
    2. Label Generation (Control Flow)
    3. On-Demand Compilation of Data Dependencies (Pull Model)
    4. Explicit Compilation of Control Flow (Push Model)
    """
    def __init__(self):
        self.instructions: List[Tuple[Any, ...]] = []
        self.var_counter = 0
        self.label_counter = 0
        self.port_var_map: Dict[Any, str] = {} # Map[NodePort, str]
        self.compiled_nodes: Set[Any] = set() 
        self.errors: List[str] = []

    def new_temp(self) -> str:
        """Allocate a new temporary variable (register)"""
        self.var_counter += 1
        return f"t{self.var_counter}"

    def new_label(self, prefix="L") -> str:
        """Create a new unique label for jumps"""
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"

    def emit(self, *args):
        """Emit an instruction tuple"""
        self.instructions.append(tuple(args))

    def emit_label(self, label: str):
         """Emit a definition of a label"""
         self.instructions.append(("LABEL", label))

    def set_var(self, port: Any, var_name: str):
        """
        Register that a specific Output Port's value is stored in 'var_name'.
        Downstream nodes will look this up.
        """
        self.port_var_map[port] = var_name

    def get_var(self, port: Any) -> str:
        """
        Get the variable name for an Output Port (Source).
        
        CRITICAL: If the node producing this port hasn't been compiled yet 
        (e.g., a pure math node not in the control flow), this triggers 
        'On-Demand Compilation' of that upstream node.
        """
        if port is None:
             return "NULL"
        
        if port in self.port_var_map:
            return self.port_var_map[port]
        
        # Dependency is not resolved. 
        # Trigger compilation of the upstream node (The owner of the output port)
        # This realizes the "Pull" model for data nodes.
        node = port.node
        if node not in self.compiled_nodes:
            self.compile_node(node)
            
        return self.port_var_map.get(port, "UNDEFINED")

    def compile_node(self, node: Any):
        """Compile a single node"""
        if node in self.compiled_nodes:
            return
        
        self.compiled_nodes.add(node)
        
        if hasattr(node, 'compile'):
            node.compile(self)
        else:
            self.errors.append(f"Node {node.id} ({node.type}) does not support compilation.")

    def compile_chain(self, start_node: Any):
        """
        Entry point to compile a chain of control flow nodes.
        Usually called by 'Parent' nodes (If, Loop) for their bodies,
        or by the main Compiler driver for the start node.
        """
        self.compile_node(start_node)

    def print_ir(self):
        """Print the generated assembly-like IR"""
        print("=== INTERMEDIATE REPRESENTATION ===")
        for instr in self.instructions:
            if instr[0] == "LABEL":
                print(f"{instr[1]}:")
            else:
                formatted = " ".join([str(x) for x in instr])
                print(f"  {formatted}")
        print("===================================")
