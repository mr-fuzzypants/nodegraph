
from typing import Optional, List, Dict, Any, Type, Callable, TYPE_CHECKING
import sys
import logging
from enum import Enum, auto

# To avoid circular imports
if TYPE_CHECKING:
    from NodePort import NodePort

from .NodePort import NodePort, InputDataPort, OutputDataPort, InputControlPort, OutputControlPort, ValueType, PortFunction


# Get a logger for this module
logger = logging.getLogger(__name__)

# --- RUNTIME COMMAND STRUCTS (Port-Friendly) ---
# This architecture allows the execution engine to be decoupled from the graph structure.
# In Python, recursion is fine. In Typescript (Async) and Rust (Ownership),
# we cannot simply call `node.compute()` recursively.
# Instead, `compute()` returns a Command, and a central "Runner" decides what to do next.
class ExecCommand(Enum):
    CONTINUE = auto()   # Scheduler: Add 'next_nodes' to the execution queue
    WAIT = auto()       # Scheduler: Pause execution (e.g. await Promise)
    LOOP_AGAIN = auto() # Scheduler: Re-schedule this node immediately (for iterative loops)
    COMPLETED = auto()  # Scheduler: Stop this branch of execution

class ExecutionResult:
    """
    Standardized return type for all Node execution. 
    Decouples the logic (Node) from the flow control (Runner).
    """
    def __init__(self, command: ExecCommand, next_nodes: Optional[List['Node']] = None, next_node_ids: Optional[List[str]] = None):
        self.command = command
        self.next_nodes = next_nodes if next_nodes is not None else []
        self.next_node_ids = next_node_ids if next_node_ids is not None else []



# A typescript map behaves like an ordered dict in python
class Node:
    _node_registry: Dict[str, Type['Node']] = {}

    @classmethod
    def register(cls, type_name: str) -> Callable[[Type['Node']], Type['Node']]:
        """Decorator to register a node class with a specific type name."""
        def decorator(subclass: Type['Node']) -> Type['Node']:
            cls._node_registry[type_name] = subclass
            return subclass
        return decorator

    @classmethod
    def create_node(cls, node_id: str, type_name: str, *args, **kwargs) -> 'Node':
        """Factory method to create a node instance by type name."""
        # Use simple dictionary lookup for O(1) factory
        if type_name not in cls._node_registry:
            # Fallback or strict error? 
            # For now, let's just try to be helpful or error out.
            raise ValueError(f"Unknown node type '{type_name}'")
        
        node_class = cls._node_registry[type_name]
        return node_class(node_id, type_name, *args, **kwargs)

    def __init__(self, 
                 id: str, 
                 type: str, 
                 owner: Optional[Any] = None, 
                 inputs: Optional[Dict[str, NodePort]] = None, 
                 outputs: Optional[Dict[str, NodePort]] = None):
        self.id = id
        self.type = type

        # Use Standard Dicts - Explicit Dict[str, NodePort] for TS Map<string, NodePort>
        self.inputs: Dict[str, NodePort] = inputs if inputs is not None else {}
        self.outputs: Dict[str, NodePort] = outputs if outputs is not None else {}

        self.is_flow_control_node = False
        self.is_loop_node = False 
        self._isDirty = True  
        self.owner = owner  # Parent ID or Reference? Keeping Ref for now to pass tests.

    def isNetwork(self) -> bool:
        return False

    def isDataNode(self) -> bool:
        return self.is_flow_control_node == False

    def isFlowControlNode(self) -> bool:
        return self.is_flow_control_node == True
    
    def markDirty(self):
        self._isDirty = True
        
    def markClean(self):
        self._isDirty = False

    def isDirty(self) -> bool:  
        return self._isDirty

    # TODO: NOT AT ALL TESTED
    def delete_input(self, port_name: str):
        if port_name in self.inputs:
            # TODO: logic omitted for brevity in porting step
            # Note: Removal needs to handle connection cleanup explicitly in Rust/TS
            port = self.inputs[port_name]
            # ... cleanup code ...
            del self.inputs[port_name]    

    def delete_output(self, port_name: str):
        if port_name in self.outputs:
            del self.outputs[port_name]

    
    def add_control_input(self, port_name: str) -> InputControlPort:
        port = InputControlPort(self, port_name)
        self.inputs[port_name] = port
        return port
    

    def add_control_output(self, port_name: str) -> OutputControlPort:
        port = OutputControlPort(self, port_name)
        self.outputs[port_name] = port
        return port
    

    def add_data_input(self, port_name: str, data_type: ValueType = ValueType.ANY) -> InputDataPort:
        if port_name in self.inputs:
            raise ValueError(f"Data input port '{port_name}' already exists in node '{self.id}'")
        
        port = InputDataPort(self, port_name, data_type=data_type)
        self.inputs[port_name] = port

        return port

    
    def add_data_output(self, port_name: str, data_type: ValueType = ValueType.ANY) -> OutputDataPort:
        if port_name in self.outputs:
            raise ValueError(f"Data output port '{port_name}' already exists in node '{self.id}'")
        
        port = OutputDataPort(self, port_name, data_type=data_type)
        self.outputs[port_name] = port

        return port


    # Updated helper to use Enum instead of Int Flag
    def get_input_ports(self, restrict_to: Optional[PortFunction] = None) -> List[NodePort]:
        if restrict_to is None:
            return list(self.inputs.values())
            
        return [port for port in self.inputs.values() if port.function == restrict_to]

            
    def get_output_ports(self, restrict_to: Optional[PortFunction] = None) -> List[NodePort]:
        if restrict_to is None:
            return list(self.outputs.values())
            
        return [port for port in self.outputs.values() if port.function == restrict_to]
            
    def get_output_data_ports(self) -> List[NodePort]:
        return self.get_output_ports(restrict_to=PortFunction.DATA)

    def get_output_control_ports(self) -> List[NodePort]:
        return self.get_output_ports(restrict_to=PortFunction.CONTROL)  

    def get_input_data_ports(self) -> List[NodePort]:
        return self.get_input_ports(restrict_to=PortFunction.DATA)

   
    def get_input_control_ports(self) -> List[NodePort]:
        return self.get_input_ports(restrict_to=PortFunction.CONTROL)
    
        

    def get_input_data_port(self, port_name: str) -> NodePort: 
        port = self.inputs.get(port_name)
        
        if not port:
            raise KeyError(f"Input port '{port_name}' not found in node '{self.id}'")
        if not port.isDataPort():
            raise KeyError(f"Input port '{port_name}' in node '{self.id}' is not a data port")
        
        return port
    
    def get_output_data_port(self, port_name: str) -> NodePort:
        port = self.outputs.get(port_name)
        if hasattr(port, 'isDataPort'): assert(port.isDataPort()) # type: ignore
        if not port:
            raise KeyError(f"Output port '{port_name}' not found in node '{self.id}'")
        if not port.isDataPort():
            raise KeyError(f"Output port '{port_name}' in node '{self.id}' is not a data port")
        
        return port
    
    def get_input_control_port(self, port_name: str) -> NodePort:
        port = self.inputs.get(port_name)
        if hasattr(port, 'isControlPort'): assert(port.isControlPort()) # type: ignore
        if not port:
            raise ValueError(f"Input port '{port_name}' not found in node '{self.id}'")
        if not port.isControlPort():
            raise ValueError(f"Input port '{port_name}' in node '{self.id}' is not a control port")
        
        return port
    
    def get_output_control_port(self, port_name: str) -> NodePort:
        port = self.outputs.get(port_name)
        if hasattr(port, 'isControlPort'): assert(port.isControlPort()) # type: ignore
        if not port:
            raise ValueError(f"Output port '{port_name}' not found in node '{self.id}'")
        if not port.isControlPort():
            raise ValueError(f"Output port '{port_name}' in node '{self.id}' is not a control port")
        
        return port

    def is_connected(self, port_name: str, is_input: bool = True) -> bool:
        port = self.inputs.get(port_name) if is_input else self.outputs.get(port_name)
        if not port:
            raise ValueError(f"Port '{port_name}' not found in node '{self.id}'")
        
        if is_input:
            return len(port.incoming_connections) > 0
        else:
            return len(port.outgoing_connections) > 0

    # Removed get_source_nodes / get_target_nodes logic that relies on object traversal
    # In Rust/TS, you'd query the Graph/Network with the connection IDs. 
    # For now, leaving simple accessors if necessary:
    # def get_source_nodes(self, port_name): ...
    

    def can_connect_output_to(self, from_port_name: str, other_node: 'Node', to_port_name: str) -> bool:
        from_port = self.outputs.get(from_port_name)
        to_port = other_node.inputs.get(to_port_name)

        if not from_port:
            raise ValueError(f"Output port '{from_port_name}' not found in node '{self.id}'")
        if not to_port:
            raise ValueError(f"Input port '{to_port_name}' not found in node '{other_node.id}'")
        
        # Identity check using IDs for portability
        if from_port.node.id == other_node.id:
            return False
        
        return True

    def connect_output_to(self, from_port_name: str, other_node: 'Node', to_port_name: str):
        from_port = self.outputs.get(from_port_name)
        to_port = other_node.inputs.get(to_port_name)

        if not from_port:
            raise ValueError(f"Output port '{from_port_name}' not found in node '{self.id}'")
        if not to_port:
            raise ValueError(f"Input port '{to_port_name}' not found in node '{other_node.id}'")
        
        if from_port.node.id == other_node.id:
            raise ValueError("Cannot connect a node's output to its own input")
        

        if to_port.incoming_connections:
            if to_port.isInputOutputPort() or from_port.isInputOutputPort():
                #TODO: what is this case?
                # allow multiple connections for input/output ports
                pass
            else:
                raise ValueError(f"Error: Input port '{to_port_name}' on node '{other_node.id}' is already connected")
        

        return from_port.connectTo(to_port)

        
  

    # TODO: precompute should not compute inputs. this should be done in compute() and this should be a callback only
    def precompute(self):
        logger.info(f"PRECOMPUTE: node '{self.id}' ")


    def postcompute(self):
        logger.info(f"POSTCOMPUTE: node '{self.id}' ")
        # validation checks. We're really just making sure the node is working correclty here.
        self.dump_dirty_states()
        assert(self.all_data_inputs_clean())
        
        assert(self.all_data_outputs_clean())


        self._isDirty = False
        


    # this is checking for cleen DATA inputs only
    def all_data_inputs_clean(self):
        for input_port in self.get_input_data_ports():
            if input_port._isDirty:
                return False
        return True
    

    def all_data_outputs_clean(self):
        for output_port in self.get_output_data_ports():
            if output_port._isDirty:
                return False
        return True
    
    def dump_dirty_states(self):
    
        logger.info(f"  Node '{self.id}' port dirty states:")
        logger.info(f".    Control Inputs: ({len(self.get_input_control_ports())})")
        for input_port in self.get_input_control_ports():
            logger.info(f".       Input Port [{input_port.port_name}] dirty: {input_port.isDirty()}; active: {input_port.isActive()}")
        logger.info(f".    Control Outputs: ({len(self.get_output_control_ports())})")
        for output_port in self.get_output_control_ports():
            logger.info(f".       Output Port [{output_port.port_name}] dirty: {output_port.isDirty()}; active: {output_port.isActive()}")
        logger.info(f".    Data Inputs: ({len(self.get_input_data_ports())})")
        for input_port in self.get_input_data_ports():
            logger.info(f".       Input Port [{input_port.port_name}] dirty: {input_port.isDirty()}; value: {input_port.value}")
        logger.info(f".    Data Outputs: ({len(self.get_output_data_ports())})")
        for output_port in self.get_output_data_ports():
            logger.info(f".       Output Port [{output_port.port_name}] dirty: {output_port.isDirty()}; value: {output_port.value}")
    
    def _get_nodes_from_port(self, port: NodePort) -> List['Node']:
        nodes = []
        # Support both output ports and input/output ports acting as outputs
        if hasattr(port, 'outgoing_connections'):
             for connection in port.outgoing_connections:
                 if hasattr(connection, 'to_port') and connection.to_port:
                     nodes.append(connection.to_port.node)
        return nodes

    async def compute(self) -> ExecutionResult:
        """
        [Runtime Phase]
        Executes the node's logic asynchronously.
        Returns an ExecutionResult to tell the Runner what nodes to execute next.
        """
        self.precompute()

        self.postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

    def compile(self, builder: Any):
        """
        [Compile Phase]
        Does NOT run the node. Instead, emits Intermediate Representation (IR) instructions
        to the 'builder'. This IR allows generation of AssemblyScript, WASM, or Optimized Rust.
        """
        pass
       
    
        # if any inputs are still dirty, we cannot compute this node
        # if any input ports have changed then recompute.

        pass  # Placeholder for node computation logic

    def generate_IRC(self):
        # Placeholder for generating intermediate representation code for this node
        pass