
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
  
from .Interface import IExecutionContext, IExecutionResult, INode, INodePort, IInputControlPort, IOutputControlPort, IInputDataPort, IOutputDataPort

from .Types import ValueType, PortFunction, NodeKind
from .NodePort import NodePort, InputDataPort, OutputDataPort, InputControlPort, OutputControlPort
from .GraphPrimitives import GraphNode
# Get a logger for this module
logger = logging.getLogger(__name__)


class PluginRegistry:
    _registry: Dict[str, Type['Node']] = {}

    @classmethod
    def register(cls, type_name: str) -> Callable[[Type['Node']], Type['Node']]:
        """Decorator to register a node class with a specific type name."""
        def decorator(subclass: Type['Node']) -> Type['Node']:
            if cls._registry.get(type_name):
                raise ValueError(f"Node type '{type_name}' is already registered.")
            cls._registry[type_name] = subclass
            return subclass
        return decorator
    
    @classmethod
    def get_node_class(cls, type_name: str) -> Optional[Type['Node']]:
        return cls._registry.get(type_name)
    
    @classmethod
    def create_node(cls, node_id: str, type_name: str, *args, **kwargs) -> 'Node':
        """Factory method to create a node instance by type name."""
        NodeClass = cls.get_node_class(type_name)
        if not NodeClass:
            raise ValueError(f"Unknown node type '{type_name}'")
        return NodeClass(node_id, type_name, *args, **kwargs)
    
    def get_registered_types(cls) -> List[str]:
        return list(cls._registry.keys())
    


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
                 network_id: str,
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
        self.network_id = network_id
        self.graph = None # Will be set by the NodeNetwork when added
        self.path= " path node computed at runtime " # This is a bit of a hack, but it allows us to have a path property that is computed at runtime based on the network structure. In Rust/TS, we can compute this on demand or cache it as needed.

        self.kind = NodeKind.FUNCTION

   

    def isNetwork(self) -> bool:
        return self.kind == NodeKind.NETWORK

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
    

    @staticmethod
    @abstractmethod
    async def compute(executionContext) -> IExecutionResult:
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