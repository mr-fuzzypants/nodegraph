
from collections import OrderedDict
from enum import Enum, auto
from typing import List, Optional, Any, TYPE_CHECKING, Dict
import sys

import logging

from .Types import PortDirection, PortFunction, ValueType

# Get a logger for this module
logger = logging.getLogger(__name__)

# To avoid circular imports only for typing
if TYPE_CHECKING:
    from Node import Node # Assuming Node is strictly typed

# Retain for backward compatibility in Python code, but mark as Legacy
PORT_TYPE_INPUT = 1
PORT_TYPE_OUTPUT = 2   
PORT_TYPE_INPUTOUTPUT = 4   
PORT_TYPE_OUTPUTINPUT = 8   
PORT_TYPE_CONTROL = 0x80

CONTROL_PORT = 0
DATA_PORT = 1
ANY_PORT = 2

# Legacy Alias
DataType = ValueType



        
class NodePort:
    def __init__(self, 
                 node_id: str,  # Typed as Any to avoid circular ref check at runtime in Python 
                 port_name: str, 
                 port_type: int, # Legacy int mask for now, to support existing calls
                 is_control: bool = False, 
                 data_type: ValueType = ValueType.ANY):
        
        #self.node = node
        self.node_id = node_id
        self.port_type = port_type 
        self.port_name = port_name
        self.data_type = data_type
        self._isDirty: bool = True 
        self.value: Any = self._get_default_for_type(data_type)

        # Infer new Enums from legacy flags
        self.direction = PortDirection.INPUT
        if self.port_type & PORT_TYPE_OUTPUT:
            self.direction = PortDirection.OUTPUT
        elif self.port_type & PORT_TYPE_INPUTOUTPUT:
            self.direction = PortDirection.INPUT_OUTPUT
            
        self.function = PortFunction.CONTROL if is_control or (self.port_type & PORT_TYPE_CONTROL) else PortFunction.DATA
        
        if is_control:
             self.port_type |= PORT_TYPE_CONTROL

    def _get_default_for_type(self, dtype: ValueType) -> Any:
        if dtype == ValueType.INT: return 0
        if dtype == ValueType.FLOAT: return 0.0
        if dtype == ValueType.STRING: return ""
        if dtype == ValueType.BOOL: return False
        if dtype == ValueType.ARRAY: return []
        if dtype == ValueType.DICT: return {}
        return None
    
    def markDirty(self):
        AssertionError
        # Prevent infinite recursion for cycles (though DAG should be standard)
        if self._isDirty:
            return
            
        self._isDirty = True
       

    def markClean(self):
        self._isDirty = False

    def isDirty(self) -> bool:
        return self._isDirty

  
    def isDataPort(self) -> bool:
        # return self.port_type & PORT_TYPE_CONTROL == 0
        return self.function == PortFunction.DATA
    
    def isControlPort(self) -> bool:
        # return self.port_type & PORT_TYPE_CONTROL != 0
        return self.function == PortFunction.CONTROL
    
    def isInputPort(self) -> bool:
        # return (self.port_type & PORT_TYPE_INPUT) == PORT_TYPE_INPUT
        return self.direction == PortDirection.INPUT
    
    def isOutputPort(self) -> bool:
        # return (self.port_type & PORT_TYPE_OUTPUT) == PORT_TYPE_OUTPUT
        return self.direction == PortDirection.OUTPUT
    
    def isInputOutputPort(self) -> bool:
        # return (self.port_type & PORT_TYPE_INPUTOUTPUT) == PORT_TYPE_INPUTOUTPUT
        return self.direction == PortDirection.INPUT_OUTPUT
    

    
    # TODO: should this be the default implmentation?
    def setValue(self, value: Any):
        # Strict type checking enables mapping to Rust Enums/TS Unions
        if not ValueType.validate(value, self.data_type):
             # Log warning for now, but in future (Rust) this is a compile/runtime error
             logger.warning(f"Port '{self.port_name}' expected {self.data_type}, got {type(value)}. Value={value}")
             # raise TypeError(f"Port '{self.port_name}' requires {self.data_type}, got {type(value)}")
             
        self.value = value
        self._isDirty = False
     



    # Check to see if my port is dirty. If it is, then 
    def getValue(self) -> Any:
        return self.value
    
    

# HMMM. do we need these subclasses and do we seperate control/data port types when defining ports on nodes?
class DataPort(NodePort):
    def __init__(self, node, port_name, port_type, data_type=DataType.ANY):
        super().__init__(node, port_name, port_type, data_type=data_type)
    

    #maybe fetch_value() instead.
    # 
    async def getValue(self, current_port=None):

        return self.value


class ControlPort(NodePort):
    def __init__(self, node_id, port_name, port_type):
        super().__init__(node_id, port_name, port_type | PORT_TYPE_CONTROL)



    def activate(self, current_port=None):
        self.setValue(True)
        
       
    
    def deactivate(self):
     
        #logger.debug(f"Deactivating control port {self.port_name} on node {self.node.name}")
        self.setValue(False)

    def isActive(self):
        return self.getValue() == True
    



class InputDataPort(DataPort):
    def __init__(self, node_id, port_name, data_type=DataType.ANY):
        super().__init__(node_id, port_name, PORT_TYPE_INPUT, data_type=data_type)
        self.incoming_connections = []

class InputControlPort(ControlPort):
    def __init__(self, node_id, port_name):
        super().__init__(node_id, port_name, PORT_TYPE_INPUT | PORT_TYPE_CONTROL)
        self.incoming_connections = []

class InputOutputDataPort(DataPort):
    def __init__(self, node_id, port_name, data_type=DataType.ANY):
        super().__init__(node_id, port_name, PORT_TYPE_INPUTOUTPUT, data_type=data_type)

        self.incoming_connections = []
        self.outgoing_connections = []

class InputOutputControlPort(ControlPort):
    def __init__(self, node_id, port_name):
        super().__init__(node_id, port_name, PORT_TYPE_INPUTOUTPUT | PORT_TYPE_CONTROL)

        self.incoming_connections = []
        self.outgoing_connections = []

    

class OutputDataPort(DataPort):
    def __init__(self, node_id, port_name, data_type=DataType.ANY):
        super().__init__(node_id, port_name, PORT_TYPE_OUTPUT, data_type=data_type)
        self.outgoing_connections = []

        
class OutputControlPort(ControlPort):
    def __init__(self, node_id, port_name):
        super().__init__(node_id, port_name, PORT_TYPE_OUTPUT | PORT_TYPE_CONTROL)
        self.outgoing_connections = []


