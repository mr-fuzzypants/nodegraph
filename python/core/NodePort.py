
from collections import OrderedDict
from enum import Enum, auto
from typing import List, Optional, Any, TYPE_CHECKING, Dict
import sys

import logging


# Get a logger for this module
logger = logging.getLogger(__name__)

# To avoid circular imports only for typing
if TYPE_CHECKING:
    from Node import Node # Assuming Node is strictly typed



# 1. Use Enums for Flags (Rust/TS friendly)
class PortDirection(Enum):
    INPUT = auto()
    OUTPUT = auto()
    INPUT_OUTPUT = auto()
    # Helper to map legacy int flags if needed
    
class PortFunction(Enum):
    DATA = auto()
    CONTROL = auto()

# 2. Use Enums for Data Types (Maps directly to TS Union types / Rust Enums)
class ValueType(Enum):
    ANY = "any"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    DICT = "dict"
    ARRAY = "array"
    OBJECT = "object"
    VECTOR = "vector"
    MATRIX = "matrix"
    COLOR = "color"
    BINARY = "binary"
    
    @staticmethod
    def validate(value: Any, data_type: 'ValueType') -> bool:
        if data_type == ValueType.ANY:
            return True
        if value is None: 
            return True # Allow None? Or strictly enforce?
            
        if data_type == ValueType.INT:
            return isinstance(value, int)
        elif data_type == ValueType.FLOAT:
            return isinstance(value, (float, int)) # Allow ints to pass as floats
        elif data_type == ValueType.STRING:
            return isinstance(value, str)
        elif data_type == ValueType.BOOL:
            return isinstance(value, bool)
        elif data_type == ValueType.DICT:
            return isinstance(value, (dict, OrderedDict))
        elif data_type == ValueType.ARRAY:
            return isinstance(value, (list, tuple))
        elif data_type == ValueType.OBJECT:
            return True # Or specific class check
        elif data_type == ValueType.VECTOR:
            return isinstance(value, (list, tuple)) # Simplistic check for now
        elif data_type == ValueType.MATRIX:
            return isinstance(value, (list, tuple)) # Simplistic check
        elif data_type == ValueType.COLOR:
            return isinstance(value, (str, tuple, list)) # Hex string or RGB tuple
        elif data_type == ValueType.BINARY:
            return isinstance(value, (bytes, bytearray))
            
        return False

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
                 node: Any,  # Typed as Any to avoid circular ref check at runtime in Python 
                 port_name: str, 
                 port_type: int, # Legacy int mask for now, to support existing calls
                 is_control: bool = False, 
                 data_type: ValueType = ValueType.ANY):
        
        self.node = node
        self.port_type = port_type 
        self.port_name = port_name
        self.data_type = data_type
        self._isDirty: bool = True 
        self.value: Any = None 

        # Infer new Enums from legacy flags
        self.direction = PortDirection.INPUT
        if self.port_type & PORT_TYPE_OUTPUT:
            self.direction = PortDirection.OUTPUT
        elif self.port_type & PORT_TYPE_INPUTOUTPUT:
            self.direction = PortDirection.INPUT_OUTPUT
            
        self.function = PortFunction.CONTROL if is_control or (self.port_type & PORT_TYPE_CONTROL) else PortFunction.DATA
        
        if is_control:
             self.port_type |= PORT_TYPE_CONTROL


    
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
    

    # TDOD: implement connection management and type checking higher up in the
    # network layer?
    """
    def connectTo(self, other_port: 'NodePort'):


        logger.debug(f"Connecting port '{self.port_name}' on node '{self.node}' to port '{other_port.port_name}' on node '{other_port.node}'")
      
        if self.node == other_port.node:
            # don't do this check if either port is an input/output port
            if not self.isInputOutputPort() and not other_port.isInputOutputPort():
                # assert(False) # Removed assert false to avoid halting
                raise ValueError("Cannot connect a port to another port on the same node")
                
           
        # TYPE CHECKING 
        # Allow connection if types match, or if one of them is ANY
        if self.data_type != ValueType.ANY and other_port.data_type != ValueType.ANY:
            if self.data_type != other_port.data_type:
                 # Special case: Allow connecting Int to Float?
                 if not (self.data_type == ValueType.INT and other_port.data_type == ValueType.FLOAT):
                    raise ValueError(f"Type Mismatch: Cannot connect {self.data_type} to {other_port.data_type}")


        if not self.node.network:
             raise ValueError(f"Node {self.node.id} is not attached to a network. Cannot create connection from {self.port_name}.")

        self.node.network.add_edge(self.node.id, self.port_name, other_port.node.id, other_port.port_name)

        return None # connection removed

        # Note: Removing runtime value check here, it should be in setValue
    """ 
    
    # TODO: should this be the default implmentation?
    def setValue(self, value: Any):
        self.value = value
        self._isDirty = False

        # TYPE CHECKING.
        # TODO: Should this raise an error instead of just logging?
        if not ValueType.validate(value, self.data_type):
             logger.warning(f"Port '{self.port_name}' expected {self.data_type}, got {type(value)}")
     



    # Check to see if my port is dirty. If it is, then 
    def getValue(self) -> Any:
        return self.value
    
    # return the node that owns this port
    def portOwner(self) -> Any:
        return self.node

    



# HMMM. do we need these subclasses and do we seperate control/data port types when defining ports on nodes?
class DataPort(NodePort):
    def __init__(self, node, port_name, port_type, data_type=DataType.ANY):
        super().__init__(node, port_name, port_type, data_type=data_type)
    

    #maybe fetch_value() instead.
    # 
    async def getValue(self, current_port=None):

        return self.value


class ControlPort(NodePort):
    def __init__(self, node, port_name, port_type):
        super().__init__(node, port_name, port_type | PORT_TYPE_CONTROL)



    def activate(self, current_port=None):
        self.setValue(True)
        
       
    
    def deactivate(self):
     
        logger.debug(f"Deactivating control port {self.port_name} on node {self.node.id}")
        self.setValue(False)

    def isActive(self):
        return self.getValue() == True
    



class InputDataPort(DataPort):
    def __init__(self, node, port_name, data_type=DataType.ANY):
        super().__init__(node, port_name, PORT_TYPE_INPUT, data_type=data_type)
        self.incoming_connections = []

class InputControlPort(ControlPort):
    def __init__(self, node, port_name):
        super().__init__(node, port_name, PORT_TYPE_INPUT | PORT_TYPE_CONTROL)
        self.incoming_connections = []

class InputOutputDataPort(DataPort):
    def __init__(self, node, port_name, data_type=DataType.ANY):
        super().__init__(node, port_name, PORT_TYPE_INPUTOUTPUT, data_type=data_type)

        self.incoming_connections = []
        self.outgoing_connections = []

class InputOutputControlPort(ControlPort):
    def __init__(self, node, port_name):
        super().__init__(node, port_name, PORT_TYPE_INPUTOUTPUT | PORT_TYPE_CONTROL)

        self.incoming_connections = []
        self.outgoing_connections = []

    

class OutputDataPort(DataPort):
    def __init__(self, node, port_name, data_type=DataType.ANY):
        super().__init__(node, port_name, PORT_TYPE_OUTPUT, data_type=data_type)
        self.outgoing_connections = []

        
class OutputControlPort(ControlPort):
    def __init__(self, node, port_name):
        super().__init__(node, port_name, PORT_TYPE_OUTPUT | PORT_TYPE_CONTROL)
        self.outgoing_connections = []


