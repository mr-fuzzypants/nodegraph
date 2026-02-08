


from __future__ import annotations
from typing import Optional, List, Dict, Any, Type, Callable, TYPE_CHECKING
import sys
import logging
from enum import Enum, auto

from abc import ABC, abstractmethod

from .Types import ValueType, PortFunction, PortDirection


class INodePort(ABC):
    @abstractmethod
    def markDirty(self):
        pass
            
    @abstractmethod
    def markClean(self):
       pass

    @abstractmethod
    def isDirty(self) -> bool:
        pass

    @abstractmethod
    def isDataPort(self) -> bool:
        pass
    
    @abstractmethod
    def isControlPort(self) -> bool:
        pass
    
    @abstractmethod
    def isInputPort(self) -> bool:
        pass
    
    @abstractmethod
    def isOutputPort(self) -> bool:
        pass    
    
    @abstractmethod
    def isInputOutputPort(self) -> bool:
       pass
    
    @abstractmethod
    def setValue(self, value: Any):
        pass
     
    # Check to see if my port is dirty. If it is, then 
    @abstractmethod
    def getValue(self) -> Any:
        pass

class IInputControlPort(INodePort):
    pass

class IOutputControlPort(INodePort):
    pass

class IInputDataPort(INodePort):
    pass

class IOutputDataPort(INodePort):
    pass


# Base class for Nodes. Will be subclassed by actual node implementations. 
# Contains common properties and methods required for graph traversal.
class IGraphNode(ABC):
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

class INode(IGraphNode):
    @abstractmethod
    def isNetwork(self) -> bool:
        pass

    @abstractmethod
    def isDataNode(self) -> bool:
        pass

    @abstractmethod
    def isFlowControlNode(self) -> bool:
        pass
    
    @abstractmethod
    def isDirty(self) -> bool:
        pass
    
    @abstractmethod
    def markDirty(self):
        pass
        
    @abstractmethod
    def markClean(self):
        pass

    @abstractmethod
    def isDirty(self) -> bool:  
        pass

    @abstractmethod
    def delete_input(self, port_name: str):
        pass

    @abstractmethod
    def delete_output(self, port_name: str):
        pass

    @abstractmethod
    def add_control_input(self, port_name: str) -> IInputControlPort:
        pass
    
    @abstractmethod
    def add_control_output(self, port_name: str) -> IOutputControlPort:
        pass
    
    @abstractmethod
    def add_data_input(self, port_name: str, data_type: ValueType = ValueType.ANY) -> IInputDataPort:
        pass

    @abstractmethod
    def add_data_output(self, port_name: str, data_type: ValueType = ValueType.ANY) -> IOutputDataPort:
        pass

    @abstractmethod
    def get_input_ports(self, restrict_to: Optional[PortFunction] = None) -> List[INodePort]:
        pass
           
    @abstractmethod   
    def get_output_ports(self, restrict_to: Optional[PortFunction] = None) -> List[INodePort]:
        pass
            
    @abstractmethod   
    def get_output_data_ports(self) -> List[INodePort]:
       pass

    @abstractmethod
    def get_output_control_ports(self) -> List[INodePort]:
        pass 

    @abstractmethod
    def get_input_data_ports(self) -> List[INodePort]:
        pass

    @abstractmethod
    def get_input_control_ports(self) -> List[INodePort]:
        pass
    
        

    def get_input_data_port(self, port_name: str) -> INodePort: 
        pass
    
    @abstractmethod
    def get_output_data_port(self, port_name: str) -> INodePort:
        pass
    
    @abstractmethod
    def get_input_control_port(self, port_name: str) -> INodePort:
        pass
        
    
    @abstractmethod
    def get_output_control_port(self, port_name: str) -> INodePort:
        pass


    # TODO: precompute should not compute inputs. this should be done in compute() and this should be a callback only
    @abstractmethod
    def precompute(self):
      pass

    @abstractmethod
    def postcompute(self):
        pass
        


    @abstractmethod
    def all_data_inputs_clean(self):
        pass
    
    @abstractmethod
    def all_data_outputs_clean(self):
        pass
    
    
    @abstractmethod
    async def compute(self, executionContext) -> IExecutionResult:
        pass

    @abstractmethod
    def compile(self, builder: Any):
        pass

    @abstractmethod
    def generate_IRC(self):
        pass


class INodeNetwork(INode):
    pass

class IExecutionContext(ABC):


    @abstractmethod
    def get_port_value(self, port) -> Dict[str, Any]:
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def from_dict(self, context_dict: Dict[str, Any]):
        pass



class IExecutionResult(ABC):

    @abstractmethod
    def deserialize_result(self, node: 'INode'):
        pass


class NetworkRunnerInterface(ABC):
    pass