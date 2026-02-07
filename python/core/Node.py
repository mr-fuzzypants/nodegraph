
from typing import Optional, List, Dict, Any, Type, Callable, TYPE_CHECKING
import sys
import logging
from enum import Enum, auto

from abc import ABC, abstractmethod

import uuid
import random

# To avoid circular imports
if TYPE_CHECKING:
    from NodePort import NodePort
  
from .Interface import ExecutionContextInterface, ExecutionResultInterface, INode, INodePort, IInputControlPort, IOutputControlPort, IInputDataPort, IOutputDataPort

from .Types import ValueType, PortFunction
from .NodePort import NodePort, InputDataPort, OutputDataPort, InputControlPort, OutputControlPort
from .GraphPrimitives import GraphNode
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


class ExecutionResult(ExecutionResultInterface):
    
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



class ExecutionContext(ExecutionContextInterface):
  
    def __init__(self, node: 'NodeBase'):
        self.node = node
        self.network = node.network if node else None
        self.network_id = self.network.id if self.network else None

        #self.execution_trace: List[str] = []  # Trace of executed node IDs for debugging
        #self.custom_context: Dict[str, Any] = {}  # User-defined context data
        #self.logger = logger  # Logger instance for nodes to use
        #self.step_count: int = 0  # Execution step counter


    def get_port_value(self, port) -> Dict[str, Any]:
        incoming_edges = self.network.get_incoming_edges(port.node_id, port.port_name)
      
        if not incoming_edges:
            return None
        
        edge = incoming_edges[0]
        
        source_node = self.network.get_node_by_id(edge.from_node_id)
        #`print(". SOURCE NODE:", source_node.id, source_node.type)
        if source_node.isNetwork():
            #AssertionError("Source node is a Network - should not happen in this context")
            # Check outputs first (Standard Node behavior)
            source_port = source_node.outputs.get(edge.from_port_name)
            if not source_port:
                # Fallback to inputs (Tunneling/Passthrough for Network Nodes)
                #print(". SOURCE NODE IS A NETWORK - Checking Inputs for Tunneling")
                source_port = source_node.inputs.get(edge.from_port_name)
                #print(". -> SOURCE PORT FROM NETWORK INPUT:", source_port.port_name, source_port.value,  source_port.isInputOutputPort() if source_port else "None")
        else:
            source_port = source_node.outputs.get(edge.from_port_name)  

        if source_port is None:
            raise ValueError(f"Source port '{edge.from_port_name}' not found on node '{source_node.id}'")   
        
        return source_port.value

    def to_dict(self) -> Dict[str, Any]:

        
        #print("Building execution context for node:", self.node.id, self.node.type)
        data_inputs = {}
        control_inputs = {}
        for port_name, port in self.node.inputs.items():
            if port.isDataPort():
                data_inputs[port_name] = self.get_port_value(port)
            elif port.isControlPort():
                control_inputs[port_name] = self.get_port_value(port)
                #control_inputs[port_name] = port.isActive()

        result = {
            "uuid": self.node.uuid,
            "network_id": self.network_id if self.network else None,
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





# A typescript map behaves like an ordered dict in python
class Node(INode):
    _node_registry: Dict[str, Type['Node']] = {}

    @classmethod
    def register(cls, type_name: str) -> Callable[[Type['Node']], Type['Node']]:
        """Decorator to register a node class with a specific type name."""
        def decorator(subclass: Type['Node']) -> Type['Node']:
            if cls._node_registry.get(type_name):
                raise ValueError(f"Node type '{type_name}' is already registered.")
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
                 name: str, 
                 type: str, 
                 network: 'NodeNetwork',
                 inputs: Optional[Dict[str, NodePort]] = None, 
                 outputs: Optional[Dict[str, NodePort]] = None):
        
        #super().__init__(name, type, network.id if network else None)
        self.name = name
        self.id = uuid.uuid4().hex
        #self.id = uuid.uuid4().hex  # Unique identifier for the node
        self.type = type
        self.uuid = uuid.uuid4().hex  # Unique identifier for the node instance

        # Use Standard Dicts - Explicit Dict[str, NodePort] for TS Map<string, NodePort>
        self.inputs: Dict[str, NodePort] = inputs if inputs is not None else {}
        self.outputs: Dict[str, NodePort] = outputs if outputs is not None else {}

        self.is_flow_control_node = False
        self.is_loop_node = False 
        self._isDirty = True  
        #self.owner = owner  # Parent ID or Reference? Keeping Ref for now to pass tests.
        self.network = network # Reference to the container network
        self.network_id = network.id if network else None   

        self.path= " path node computed at runtime " # This is a bit of a hack, but it allows us to have a path property that is computed at runtime based on the network structure. In Rust/TS, we can compute this on demand or cache it as needed.

   

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
        port = InputControlPort(self.id, port_name)
        self.inputs[port_name] = port
        return port
    

    def add_control_output(self, port_name: str) -> OutputControlPort:
        port = OutputControlPort(self.id, port_name)
        self.outputs[port_name] = port
        return port
    

    def add_data_input(self, port_name: str, data_type: ValueType = ValueType.ANY) -> InputDataPort:
        if port_name in self.inputs:
            raise ValueError(f"Data input port '{port_name}' already exists in node '{self.id}'")
        
        port = InputDataPort(self.id, port_name, data_type=data_type)
        self.inputs[port_name] = port

        return port

    
    def add_data_output(self, port_name: str, data_type: ValueType = ValueType.ANY) -> OutputDataPort:
        if port_name in self.outputs:
            raise ValueError(f"Data output port '{port_name}' already exists in node '{self.id}'")
        
        port = OutputDataPort(self.id, port_name, data_type=data_type)
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


    # TODO: precompute should not compute inputs. this should be done in compute() and this should be a callback only
    def precompute(self):
       print(f"PRECOMPUTE: node '{self.id}' ")


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
    
        print(f"  Node '{self.id}' port dirty states:")
        print(f".    Control Inputs: ({len(self.get_input_control_ports())})")
        for input_port in self.get_input_control_ports():
            print(f".       Input Port [{input_port.port_name}] dirty: {input_port.isDirty()}; active: {input_port.isActive()}")
        print(f".    Control Outputs: ({len(self.get_output_control_ports())})")
        for output_port in self.get_output_control_ports():
            print(f".       Output Port [{output_port.port_name}] dirty: {output_port.isDirty()}; active: {output_port.isActive()}")
        print(f".    Data Inputs: ({len(self.get_input_data_ports())})")
        for input_port in self.get_input_data_ports():
            print(f".       Input Port [{input_port.port_name}] dirty: {input_port.isDirty()}; value: {input_port.value}")
        print(f".    Data Outputs: ({len(self.get_output_data_ports())})")
        for output_port in self.get_output_data_ports():
            print(f".       Output Port [{output_port.port_name}] dirty: {output_port.isDirty()}; value: {output_port.value}")
    

    
    @abstractmethod
    async def compute(self, executionContext) -> ExecutionResult:
        pass

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