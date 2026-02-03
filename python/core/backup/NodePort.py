
from collections import OrderedDict
from enum import Enum, auto
from typing import List, Optional, Any, TYPE_CHECKING
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

        # Initialize connection lists based on direction to avoid attribute errors
        # (Though legacy code seems to just append to specific lists in subclasses, 
        # base class init should be safe)
        self.incoming_connections: List['Connection'] = []
        self.outgoing_connections: List['Connection'] = []

    
    def markDirty(self):
        # Prevent infinite recursion for cycles (though DAG should be standard)
        if self._isDirty:
            return
            
        self._isDirty = True
        
        # Propagate dirty state downstream
        # If I am an output port (or InputOutput acting as output), 
        # I must notify the input ports connected to me.
        if self.isOutputPort() or self.isInputOutputPort():
             for connection in self.outgoing_connections:
                 if connection.to_port:
                     # Mark the connected input port dirty
                     connection.to_port.markDirty()
                     # And mark its owning node dirty so it knows it needs re-compute
                     connection.to_port.node.markDirty()

    def markClean(self):
        self._isDirty = False

    def isDirty(self) -> bool:
        return self._isDirty


    def addIncomingConnection(self, connection: 'Connection'):
        self.incoming_connections.append(connection)

    def addOutgoingConnection(self, connection: 'Connection'):
        self.outgoing_connections.append(connection)


  
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
    

    def connectTo(self, other_port: 'NodePort'):

        logger.debug(f"Connecting port '{self.port_name}' on node '{self.node}' to port '{other_port.port_name}' on node '{other_port.node}'")
      
        if self.node == other_port.node:
            # don't do this check if either port is an input/output port
            if not self.isInputOutputPort() and not other_port.isInputOutputPort():
                # assert(False) # Removed assert false to avoid halting
                raise ValueError("Cannot connect a port to another port on the same node")
                
           
        # --- TYPE CHECKING CONNECTION ---
        # Allow connection if types match, or if one of them is ANY
        if self.data_type != ValueType.ANY and other_port.data_type != ValueType.ANY:
            if self.data_type != other_port.data_type:
                 # Special case: Allow connecting Int to Float?
                 if not (self.data_type == ValueType.INT and other_port.data_type == ValueType.FLOAT):
                    raise ValueError(f"Type Mismatch: Cannot connect {self.data_type} to {other_port.data_type}")
        # -------------------------------

        connection = Connection(self.node, self, other_port.node, other_port)

        self.outgoing_connections.append(connection)
        other_port.incoming_connections.append(connection)

        return connection

        # Note: Removing runtime value check here, it should be in setValue
        
    
    # TODO: should this be the default implmentation?
    def setValue(self, value: Any):
        # --- TYPE CHECKING RUNTIME ---
        if not ValueType.validate(value, self.data_type):
             # Don't throw for now, just print warning, or maybe strict mode?
             logger.error(f"Port '{self.port_name}' expected {self.data_type}, got {type(value)}")
        # -----------------------------|- 
        
        self.value = value
        self._isDirty = False

        if self.isOutputPort() or self.isInputOutputPort():
            logger.debug(f"....Marking connected ports for '{self.node.id}.{self.port_name}' dirty due to output value change")
            for connection in self.outgoing_connections:
                logger.debug(f".     |- Marking '{self.node.id}.{self.port_name}' -> '{connection.to_port.node.id}.{connection.to_port.port_name} dirty.' ")
                to_port = connection.to_port
                to_port.markDirty()
                to_port.node.markDirty()
                # was this...
                #to_port._isDirty = True  # Mark connected input port as dirty when value changes
                #to_port.node.markDirty()  # Mark the node as dirty as well


    # Check to see if my port is dirty. If it is, then 
    def getValue(self) -> Any:
        return self.value
    
    # return the node that owns this port
    def portOwner(self) -> Any:
        return self.node

    def get_source(self) -> Optional['NodePort']:
        """
        Returns the data source (Output Port) connected to this Input Port.
        Required for the Compiler/Builder to traverse the data graph backwards.
        """
        if self.incoming_connections:
            # Assumes 1 connection for data ports, which is standard
            return self.incoming_connections[0].from_port
        return None








# HMMM. do we need these subclasses and do we seperate control/data port types when defining ports on nodes?
class DataPort(NodePort):
    def __init__(self, node, port_name, port_type, data_type=DataType.ANY):
        super().__init__(node, port_name, port_type, data_type=data_type)
    

    def getDirtyDataNodes(self, incoming_connection, dirty_nodes = None):
        
        if dirty_nodes is None:
            nodes = []
        else:
            nodes = dirty_nodes

        #MARKER FOR UNDO


        
        node = incoming_connection.from_port.node
        #node._isDirty = True # why is this here? it's forcing a recook
        
        #if node.isDataNode() and node._isDirty:
        if node.isDirty():
            if node not in nodes:
                if node.isDataNode():
                    nodes.append(node)
            logger.debug(f".       Walking data node '{node.id}': isDataNode: {node.isDataNode()}; isDirty: {node._isDirty}")
            for input_port in node.get_input_data_ports():
                for connection in input_port.incoming_connections:
                    if connection.from_port.isInputOutputPort():
                        #TODO: need to check if it's connected or not
                        logger.debug(f"       !!!! TODO: Handling input/output port during dirty node walk: {connection.from_port.port_name} on node: {connection.from_port.node.id}")
                        self.getDirtyDataNodes(connection, nodes)
                    node = connection.from_port.node
                    logger.debug(f".       Walking upstream data node '{node.id}.{connection.from_port.port_name}': isDataNode: {node.isDataNode()}; isDirty: {node._isDirty}")
                    # NUST ADDED THESE TWO LINES
                    if node.isDataNode() and node._isDirty:
                        if node not in nodes:
                            nodes.append(node)
                    self.getDirtyDataNodes(connection, nodes)

               
        return nodes



    #maybe fetch_value() instead.
    # 
    async def getValue(self, current_port=None):
        """
        Rules:
        - if a port is clean, I can return the value if it's an input or output port.
        - if a port is an output port and it's dirty, it is an error as it indicates the node that owns it hasn't been
            computed yet.
        - if a port is an input port and it's dirty, then we need to fetch the value from the source port. If the source
            port is dirty, we need to compute the source node first.

        TODO: what happens if this is an input/output port?
        
        """
        if current_port is None:
            current_port = self

        logger.debug(f" getValue('{current_port.node.id}.{current_port.port_name}') isDirty: {current_port._isDirty}")
        
        # this is to look for dirty data nodes. Data nodees do not have implicit control flow 
        # so we need to trace back from the port to find dirty nodes and compute them first.
        # NOTE: the current port might actually be clean in this case. An example is a key extractor
        # NOTE: node that has a clean output port but the input port is dirty. We need to trace back 
        # NOTE: from the input port
        if current_port.isInputPort():
            if len(current_port.incoming_connections) > 0:
                source_port = current_port.incoming_connections[0].from_port

                logger.debug(f".   Getting dirty data nodes connected to '{current_port.node.id}.{current_port.port_name}'")
                dirty_nodes =source_port.getDirtyDataNodes( current_port.incoming_connections[0])

                logger.debug(f".   Dirty nodes that require compute:")
                for n in dirty_nodes:
                    logger.debug(f"       '{n.id}'")

                while dirty_nodes:
                    dirty_node = dirty_nodes.pop()
                    await dirty_node.compute()
                    
       # MARKER
        # it it's an input/output port, we treat it as an input port for now.
        if current_port._isDirty:
            # for a dirty input port, we need to fetch a clean source. It may be that the source node/port is also dirty
            # and we'd have to cook it. If it's clean we can just fetch the value.
            if current_port.isInputPort() or current_port.isInputOutputPort():
                connections = current_port.incoming_connections
                if len(connections) == 0:
                    raise ValueError(f"Cannot get value for port '{self.port_name}' on node '{self.node.id}' because it has no connections")  
                
                # a data input port can/should have only one connection
                assert(len(connections) == 1)
                source_port = connections[0].from_port

                dirty_nodes =source_port.getDirtyDataNodes(connections[0])

                logger.debug(f".   Dirty nodes that require compute:")
                for n in dirty_nodes:
                    logger.debug(f"       '{n.id}'")

                
                while dirty_nodes:
                    dirty_node = dirty_nodes.pop()
                    logger.debug(f" ........    Computing dirty node: {dirty_node.id}")
                    await dirty_node.compute()

                #assert(source_port.isInputOutputPort() == False), "Source port cannot be an input port"

                # the source port or node is dirty so we need to compute it first
                if source_port._isDirty or source_port.node._isDirty:
                    if source_port.isInputOutputPort():
                        if len(source_port.incoming_connections) >0 :
                            incoming_conn = source_port.incoming_connections[0]
                            logger.debug(f" ........Tracing back to source port for input/output port: '{source_port.node.id}.{source_port.port_name}' -> '{incoming_conn.from_port.node.id}.{incoming_conn.from_port.port_name}'")
                            result = await source_port.getValue(incoming_conn.from_port)
                            logger.debug(f" ........    Setting value for input/output port: {source_port.port_name} value: {result}")
                            source_port.value = result


            # If this is an INPUT port, we need to grab the value from the upstream OUTPUT port.
            # Upstream compute() logic sets the OUTPUT port value, but it doesn't push it deeper into the receiving input port attribute.
            # So here we pull it.
            if current_port.isInputPort():
                 assert(len(current_port.incoming_connections) > 0)
                 source_port = current_port.incoming_connections[0].from_port
                 # The source port should now be clean and have a value from the upstream compute
                 current_port.value = source_port.value
                 current_port._isDirty = False
                 
        return current_port.value

        return current_port.value


    def setValue(self, value):
        logger.debug(f". Setting  output port '{self.node.id}.{self.port_name}' dirty.")
        self.value = value
        self._isDirty = False
        if self.isOutputPort() or self.isInputOutputPort() :
            for connection in self.outgoing_connections:
                to_port = connection.to_port
                logger.debug(f".    Setting connected output port '{self.node.id}.{self.port_name}' -> '{to_port.node.id}.{to_port.port_name}' dirty.")
            
                to_port._isDirty = True  # Mark connected input port as dirty when value changes
                to_port.node._isDirty = True  # Mark the node as dirty as well

class ControlPort(NodePort):
    def __init__(self, node, port_name, port_type):
        super().__init__(node, port_name, port_type | PORT_TYPE_CONTROL)



    def activate(self, current_port=None):
        logger.debug(f"Activating control port '{self.node.id}.{self.port_name}'")
        assert(self.isControlPort())
        assert(self.isOutputPort() or self.isInputOutputPort())

        if current_port is None:
            current_port = self

        #logger.debug(f"  Control port '{self.node.id}.{self.port_name}' is an output port.")
        #if self.isOutputPort():
        #    logger.debug(f"  Control port '{self.node.id}.{self.port_name}' is an output port.")
        #elif self.isInputOutputPort():
        #    logger.debug(f"  Control port '{self.node.id}.{self.port_name}' is an input/output port.")
        #assert(len(self.outgoing_connections) > 0), "Control port has no outgoing connections to activate"

        # TODO: revisit how activation states should work when forward-cooking the graph. I.E which sides
        # TODO: of the conection gets activated and who is responsible for deactivating ports.
        current_port.setValue(True)                 # set source port value to active
        for connection in self.outgoing_connections: # set all the dest porits to active
            to_port = connection.to_port
            to_port.setValue(True)

            if to_port.isInputOutputPort():
                logger.debug(f"  >>>>> TODO: Propagating activation through input/output port: {to_port.port_name} on node: {to_port.node.id}")
                logger.debug(f"........Activating control port '{to_port.node.id}.{to_port.port_name}'")
                # Recursively activate through input/output ports
                to_port.activate(to_port)
            # If the connected port is an output/input port, we need to propagate the activation further
            #while to_port and (to_port.isInputOutputPort() ):
            #    to_port = to_port.outgoing_connections[0].to_port
            #    to_port.setValue(True)

            # Mark the connected input port as active
        # Placeholder for activating control port
            logger.debug(f"........Activating control port '{current_port.node.id}.{current_port.port_name}'")
    
        #self.setValue(True)
    
    def deactivate(self):
        #for connection in self.connections:
        #    to_port = connection.to_port
        #    to_port.setValue(False)
        # Placeholder for deactivating control port
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



class Connection:
    def __init__(self, from_node, from_port, to_node, to_port):
        # Store IDs for Arena pattern, but keep object refs for now to pass existing tests
        # or update them. The prompt asks to "convert".
        self.from_node = from_node # Keep for now as legacy support if needed, or remove?
        self.to_node = to_node     
        
        # New Arena fields
        self.from_node_id = from_node.id if hasattr(from_node, 'id') else str(from_node)
        self.to_node_id = to_node.id if hasattr(to_node, 'id') else str(to_node)
        
        self.from_port = from_port
        self.to_port = to_port