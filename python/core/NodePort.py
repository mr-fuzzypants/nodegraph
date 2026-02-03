
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

class ExecutionContext:
    """
    Context object passed to nodes during execution.
    Can hold references to the network, global state, etc.
    """
    def __init__(self, node: 'Node'):
        self.node = node
        self.network = node.network if node else None

        #self.execution_trace: List[str] = []  # Trace of executed node IDs for debugging
        #self.custom_context: Dict[str, Any] = {}  # User-defined context data
        #self.logger = logger  # Logger instance for nodes to use
        #self.step_count: int = 0  # Execution step counter

    def to_dict(self) -> Dict[str, Any]:

        data_inputs = {}
        control_inputs = {}
        for port_name, port in self.node.inputs.items():
            if port.isDataPort():
                data_inputs[port_name] = port.value
            elif port.isControlPort():
                control_inputs[port_name] = port.isActive()

        result = {
            "data_inputs": data_inputs,
            "control_inputs": control_inputs
        }

        print("!!!!!!!! NODE PORT EXECUTION CONTEXT", self.node.id, self.node.type, result)
        return result

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

class Connection:
    # Legacy connection class retained for temporary compatibility if needed by external scripts,
    # but the core logic now avoids using it.
    def __init__(self, from_node, from_port, to_node, to_port):
        self.from_node = from_node
        self.from_port = from_port
        self.to_node = to_node
        self.to_port = to_port
        
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
        # self.incoming_connections: List['Connection'] = []
        # self.outgoing_connections: List['Connection'] = []

    
    def markDirty(self):
        AssertionError
        # Prevent infinite recursion for cycles (though DAG should be standard)
        if self._isDirty:
            return
            
        self._isDirty = True
        

        # I DON"T THING WE NEED THE REST OF THIS SHIT

        # If I am an Input port, my Node needs to be marked dirty
        if self.isInputPort() and self.node:
             self.node.markDirty()
        
        # Propagate dirty state downstream
        # If I am an output port (or InputOutput acting as output), 
        # I must notify the input ports connected to me.
        if self.isOutputPort() or self.isInputOutputPort():
             # Access edges via Network
             if self.node.network:
                 outgoing_edges = self.node.network.get_outgoing_edges(self.node.id, self.port_name)
                 for edge in outgoing_edges:
                     # Find target node
                     target_node = self.node.network.get_node(edge.to_node_id)
                     if target_node:
                         target_port = target_node.inputs.get(edge.to_port_name) # Assuming input port
                         if target_port:
                             target_port.markDirty()
                             target_node.markDirty()

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

        if not self.node.network:
             raise ValueError(f"Node {self.node.id} is not attached to a network. Cannot create connection from {self.port_name}.")

        self.node.network.add_edge(self.node.id, self.port_name, other_port.node.id, other_port.port_name)

        return None # connection removed

        # Note: Removing runtime value check here, it should be in setValue
        
    
    # TODO: should this be the default implmentation?
    def setValue(self, value: Any):
        #ssert(Fal("NodePort.setValue is deprecated, use NodePort.value directly")
        # --- TYPE CHECKING RUNTIME ---
        if not ValueType.validate(value, self.data_type):
             logger.warning(f"Port '{self.port_name}' expected {self.data_type}, got {type(value)}")
        # -----------------------------|- 
        
        self.value = value
        self._isDirty = False

        if self.isOutputPort() or self.isInputOutputPort():
            logger.debug(f"....Marking connected ports for '{self.node.id}.{self.port_name}' dirty due to output value change")
            
            # New Logic: Get edges from Network
            if self.node.network:
                outgoing_edges = self.node.network.get_outgoing_edges(self.node.id, self.port_name)
                
                for edge in outgoing_edges:
                    logger.debug(f".     |- Marking '{self.node.id}.{self.port_name}' -> '{edge.to_node_id}.{edge.to_port_name} dirty.' ")
                    target_node = self.node.network.get_node(edge.to_node_id)
                    if target_node:
                        # Assuming inputs usually
                        target_port = target_node.inputs.get(edge.to_port_name)
                        if target_port:
                            target_port.markDirty()
                        target_node.markDirty()



    # Check to see if my port is dirty. If it is, then 
    def getValue(self) -> Any:
        return self.value
    
    # return the node that owns this port
    def portOwner(self) -> Any:
        return self.node

    def get_source(self) -> Optional['NodePort']:
    
        #AssertionError("NodePort.get_source is deprecated, use NodePort.get_source_port directly")
        """
        Returns the data source (Output Port) connected to this Input Port.
        Required for the Compiler/Builder to traverse the data graph backwards.
        """
        network = self.node.network
        
        # Special handling for Nodes that are Networks themselves (Root Networks)
        # where the connection might be internal (e.g. a parameter node inside driving the network input)
        if not network and hasattr(self.node, 'get_incoming_edges'):
             network = self.node

        if network:
            incoming_edges = network.get_incoming_edges(self.node.id, self.port_name)
            if incoming_edges:
                edge = incoming_edges[0]
                source_node = network.get_node(edge.from_node_id)
                if source_node:
                    # Retrieve the port object from the source node
                    # This assumes standard node structure where outputs are accessible
                    if hasattr(source_node, 'outputs') and edge.from_port_name in source_node.outputs:
                        return source_node.outputs[edge.from_port_name]
                    
                    # Support for "Passthrough" or "Tunneling" from Network Inputs
                    # An edge starting from a Network Input acts as a Source for internal nodes
                    if hasattr(source_node, 'inputs') and edge.from_port_name in source_node.inputs:
                        return source_node.inputs[edge.from_port_name]

                    # Fallback for control ports or undefined structure
                    # Ideally Node would have get_port(name)
        return None








# HMMM. do we need these subclasses and do we seperate control/data port types when defining ports on nodes?
class DataPort(NodePort):
    def __init__(self, node, port_name, port_type, data_type=DataType.ANY):
        super().__init__(node, port_name, port_type, data_type=data_type)
    

    def getDirtyDataNodes(self, incoming_connection, dirty_nodes = None):
        AssertionError("DataPort.getDirtyDataNodes is deprecated, use NodePort.getDirtyDataNodes directly")
        if dirty_nodes is None:
            nodes = []
        else:
            nodes = dirty_nodes

        #MARKER FOR UNDO

        #assert(False, "DataPort.getDirtyDataNodes is deprecated, use NodePort.getDirtyDataNodes directly")
        
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

        #assert(False), "NodePort.getValue is deprecated, use NodePort.value directly"
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
        
        # Helper to resolve graph context (where edges are stored)
        graph_context = current_port.node.network
        if not graph_context and hasattr(current_port.node, "get_incoming_edges"):
             # Fallback: Maybe the node itself is the network (Root Network case)
             graph_context = current_port.node

        logger.debug(f" getValue('{current_port.node.id}.{current_port.port_name}') isDirty: {current_port._isDirty}")
        
        # this is to look for dirty data nodes. Data nodees do not have implicit control flow 
        # so we need to trace back from the port to find dirty nodes and compute them first.
        # NOTE: the current port might actually be clean in this case. An example is a key extractor
        # NOTE: node that has a clean output port but the input port is dirty. We need to trace back 
        # NOTE: from the input port
        if current_port.isInputPort():

             # New Logic: Query Network for incoming edges
             if graph_context:
                 incoming_edges = graph_context.get_incoming_edges(current_port.node.id, current_port.port_name)
                 
                 logger.debug(f".   Getting dirty data nodes connected to '{current_port.node.id}.{current_port.port_name}'")
                 
                 if incoming_edges:
                     # For data ports, usually single input. 
                     # We need to map the EDGE back to a PORT on the SOURCE NODE to reuse the old 'getDirtyDataNodes' logic
                     # OR rewrite getDirtyDataNodes to work with Edges.
                     # Let's map it for minimal diff:
                     edge = incoming_edges[0]
                     source_node = graph_context.get_node(edge.from_node_id)
                     if source_node:
                         source_port = source_node.outputs.get(edge.from_port_name) # Assumption
                         # Handle Tunneling (Source is a Network Input)
                         if not source_port and hasattr(source_node, "inputs"):
                            source_port = source_node.inputs.get(edge.from_port_name)

                         if source_port:
                             # We need to pass a "Connection-like" object to getDirtyDataNodes because it expects it.
                             # Let's create a temporary fake connection wrapper to satisfy the legacy signature
                             fake_connection = Connection(source_node, source_port, current_port.node, current_port)
                             
                             dirty_nodes = source_port.getDirtyDataNodes(fake_connection)

                             logger.debug(f".   Dirty nodes that require compute:")
                             for n in dirty_nodes:
                                 logger.debug(f"       '{n.id}'")

                             while dirty_nodes:
                                 dirty_node = dirty_nodes.pop()
                                 execution_context = ExecutionContext(dirty_node).to_dict()
                                 await dirty_node.compute(executionContext=execution_context)
                    
       # MARKER
        # it it's an input/output port, we treat it as an input port for now.
        if current_port._isDirty:
            # for a dirty input port, we need to fetch a clean source. It may be that the source node/port is also dirty
            # and we'd have to cook it. If it's clean we can just fetch the value.
            if current_port.isInputPort() or current_port.isInputOutputPort():
                
                # New Logic:
                if not graph_context:
                     # If no context, and we are dirty, maybe we just have no value?
                     # Or assume disconnected?
                     # raise ValueError(f"Node '{current_port.node.id}' detached from network, cannot fetch input '{current_port.port_name}'")
                     pass # Maybe it's a loose node matching old tests
                
                incoming_edges = []
                if graph_context:
                    incoming_edges = graph_context.get_incoming_edges(current_port.node.id, current_port.port_name)
                elif hasattr(current_port.node, 'get_incoming_edges'):
                    # Fallback: Check if the node itself is a Network with internal loopback/feedback
                    incoming_edges = current_port.node.get_incoming_edges(current_port.node.id, current_port.port_name)

                if len(incoming_edges) == 0:
                    # No connection, value remains what it is (None or Default)
                    # Just mark clean? Or raise?
                    # Warning: if we mark clean without value, we might pass None.
                    pass
                    # raise ValueError(f"Cannot get value for port '{self.port_name}' on node '{self.node.id}' because it has no connections")  
                
                else: 
                    # a data input port can/should have only one connection
                    assert(len(incoming_edges) == 1)
                    edge = incoming_edges[0]
                    
                    source_node = graph_context.get_node(edge.from_node_id)
                    source_port = source_node.outputs.get(edge.from_port_name)

                    # Handle Tunneling (Source is a Network Input)
                    if source_port is None:
                        source_port = source_node.inputs.get(edge.from_port_name)

                    if not source_port:
                        raise ValueError(f"Source port '{edge.from_port_name}' not found on node '{edge.from_node_id}'")
                    if not source_port and hasattr(source_node, "inputs"):
                        source_port = source_node.inputs.get(edge.from_port_name)

                    if source_port:
                        fake_connection = Connection(source_node, source_port, current_port.node, current_port)
                        dirty_nodes = source_port.getDirtyDataNodes(fake_connection)
                        while dirty_nodes:
                            dirty_node = dirty_nodes.pop()
                            logger.debug(f" ........    Computing dirty node: {dirty_node.id}")
                            execution_context = ExecutionContext(dirty_node).to_dict()
                            await dirty_node.compute(executionContext=execution_context)
                        
                        # If source is a Tunnel (Input Port), we must recurse up!
                        if source_port.isInputPort() or source_port.isInputOutputPort():
                             current_port.value = await source_port.getValue()
                        else:
                             # Standard Output Port (Value should be ready from compute)
                             current_port.value = source_port.value

                    current_port._isDirty = False
        
        return current_port.value

class ControlPort(NodePort):
    def __init__(self, node, port_name, port_type):
        super().__init__(node, port_name, port_type | PORT_TYPE_CONTROL)



    def activate(self, current_port=None):
        
        #assert(False), "ControlPort.activate is deprecated, use setValue(True) directly"
        #AssertionError("ControlPort.activate is deprecated, use setValue(True) directly")
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
        
        # New Logic: Get edges from Network
        if self.node.network:
            outgoing_edges = self.node.network.get_outgoing_edges(self.node.id, self.port_name)
            
            for edge in outgoing_edges:
                target_node = self.node.network.get_node(edge.to_node_id)
                if not target_node: continue
                
                # Assuming control ports are inputs on the target
                to_port = target_node.inputs.get(edge.to_port_name) 
                
                # Or outputs if complex flow?
                if not to_port:
                     # Check outputs (for network relay)?
                     to_port = target_node.outputs.get(edge.to_port_name)

                if to_port:
                    to_port.setValue(True)

                    if to_port.isInputOutputPort():
                        logger.debug(f"  >>>>> TODO: Propagating activation through input/output port: {to_port.port_name} on node: {to_port.node.id}")
                        logger.debug(f"........Activating control port '{to_port.node.id}.{to_port.port_name}'")
                        # Recursively activate through input/output ports
                        to_port.activate(to_port)


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