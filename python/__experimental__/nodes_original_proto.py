

from collections import OrderedDict

PORT_TYPE_INPUT = 1
PORT_TYPE_OUTPUT = 2   
PORT_TYPE_INPUTOUTPUT = PORT_TYPE_INPUT | PORT_TYPE_OUTPUT # this is a bitwise OR - should we do it this way?
PORT_TYPE_RESERVED2 = 4
PORT_TYPE_RESERVED3 = 8
PORT_TYPE_RESERVED4 = 16
PORT_TYPE_RESERVED5 = 32
PORT_TYPE_RESERVED6 = 64
PORT_TYPE_CONTROL = 0x80

CONTROL_PORT = 0
DATA_PORT = 1
ANY_PORT = 2


class NodeNetwork:
    def __init__(self):
        self.nodes = OrderedDict()
    
    def add_node(self, node):
        self.nodes[node.id] = node
    
    def get_node(self, node_id):
        return self.nodes.get(node_id)
    

    def compute_step(self, start_nodes=None):
        # If start_nodes is provided, only compute from those nodes):

        if start_nodes:
            compute_nodes = start_nodes
            for cur_node in compute_nodes:
                print("Computing from start node:", cur_node.id)
                cur_node.compute()

            for cur_node in compute_nodes:           
                # find next nodes to compute based on control flow
                next_nodes = []
                print("Finding next nodes to compute...")
                for output_port in cur_node.get_output_control_ports():
                    print("Output control port:", output_port.port_id)
                    for connection in output_port.connections:
                        print("  connection to node:", connection.to_port.node.id, connection.to_port.isActive() )
                        if connection.to_port.isActive():
                            next_node = connection.to_port.node
                            #if not next_node.is_loop_node:
                            next_nodes.append(connection.to_port.node)

            #for next_node in next_nodes:
            #    next_node.compute()
            return next_nodes
            #self.compute(next_nodes)

    def compute(self, start_nodes=None):


        next_nodes = start_nodes
        while (1):
            next_nodes = self.compute_step(next_nodes)
            if not next_nodes:
                break


    

# A typescript map behaves like an ordered dict in python
class Node:
    def __init__(self, id, type, inputs=None, outputs=None):
        self.id = id
        self.type = type
        # TODO: should I seperate out data inputs/outputs from control inputs/outputs?
        self.inputs = inputs if inputs is not None else OrderedDict()
        self.outputs = outputs if outputs is not None else OrderedDict()

        self.is_flow_control_node = False

        self.is_loop_node = False # set to true for loop nodes

    def add_input(self, port_id, port_type, is_control=False):
        port = NodePort(self, port_id, port_type, is_control)
        self.inputs[port_id] = port
        return port

    def add_output(self, port_id, port_type, is_control=False):
        port = NodePort(self, port_id, port_type, is_control)
        self.outputs[port_id] = port
        return port
    
    def add_control_input(self, port_id):
        port = ControlPort(self, port_id, PORT_TYPE_INPUT)
        self.inputs[port_id] = port
        return port
    
        # TODO: was this. is it better?
        #self.is_flow_control_node = True
        #return self.add_input(port_id, PORT_TYPE_INPUT, is_control=True)

    def add_control_output(self, port_id):

        port = ControlPort(self, port_id, PORT_TYPE_OUTPUT)
        self.outputs[port_id] = port
        return port
    
        # TODO: was this. is it better?
        #self.is_flow_control_node = True
        #return self.add_output(port_id, PORT_TYPE_OUTPUT, is_control=True)
    

    def add_data_input(self, port_id):
        port = DataPort(self, port_id, PORT_TYPE_INPUT)
        self.inputs[port_id] = port

        return port

        # TODO: was this: (is it better?)
        #return self.add_input(port_id, PORT_TYPE_INPUT, is_control=False)
    
    def add_data_output(self, port_id):
        port = DataPort(self, port_id, PORT_TYPE_OUTPUT)
        self.outputs[port_id] = port

        return port
    
        # TODO: was this: (is it better?)
        #return self.add_output(port_id, PORT_TYPE_OUTPUT, is_control=False)


    # restrict_to filters out coontrol, data or both port types
    def get_input_ports(self, restrict_to=None):
        if restrict_to is None:
            return list(self.inputs.values())
        else:
            if restrict_to == CONTROL_PORT:
                return [port for port in self.inputs.values() if port.port_type & PORT_TYPE_CONTROL != 0]
            elif restrict_to == DATA_PORT:
                return [port for port in self.inputs.values() if port.port_type & PORT_TYPE_CONTROL == 0 ]
            else:
                return []
            
    def get_output_ports(self, restrict_to=None):
        if restrict_to is None:
            return list(self.outputs.values())
        else:
            if restrict_to == CONTROL_PORT:
                return [port for port in self.outputs.values() if port.port_type & PORT_TYPE_CONTROL != 0 ]
            elif restrict_to == DATA_PORT:
                return [port for port in self.outputs.values() if port.port_type & PORT_TYPE_CONTROL == 0 ]
            else:
                return []
            
    def get_output_data_ports(self):
        return self.get_output_ports(restrict_to=DATA_PORT)

    def get_output_control_ports(self):
        return self.get_output_ports(restrict_to=CONTROL_PORT)  

    def get_input_data_ports(self):
        return self.get_input_ports(restrict_to=DATA_PORT)

   
    def get_input_control_ports(self):
        return self.get_input_ports(restrict_to=CONTROL_PORT)
        

    def get_input_data_port(self, port_id): 
        port = self.inputs.get(port_id)
        if not port:
            raise ValueError(f"Input port '{port_id}' not found in node '{self.id}'")
        if not port.isDataPort():
            raise ValueError(f"Input port '{port_id}' in node '{self.id}' is not a data port")
        
        return port
    
    def get_output_data_port(self, port_id):
        port = self.outputs.get(port_id)
        if not port:
            raise ValueError(f"Output port '{port_id}' not found in node '{self.id}'")
        if not port.isDataPort():
            raise ValueError(f"Output port '{port_id}' in node '{self.id}' is not a data port")
        
        return port
    
    def get_input_control_port(self, port_id):
        port = self.inputs.get(port_id)
        if not port:
            raise ValueError(f"Input port '{port_id}' not found in node '{self.id}'")
        if not port.isControlPort():
            raise ValueError(f"Input port '{port_id}' in node '{self.id}' is not a control port")
        
        return port
    
    def get_output_control_port(self, port_id):
        port = self.outputs.get(port_id)
        if not port:
            raise ValueError(f"Output port '{port_id}' not found in node '{self.id}'")
        if not port.isControlPort():
            raise ValueError(f"Output port '{port_id}' in node '{self.id}' is not a control port")
        
        return port

    def get_source_nodes(self, port_id):
        port = self.inputs.get(port_id)
        if not port:
            raise ValueError(f"Input port '{port_id}' not found in node '{self.id}'")
        
        source_nodes = []
        for connection in port.connections:
            source_nodes.append(connection.from_node)
        return source_nodes
    
    def get_target_nodes(self, port_id):
        port = self.outputs.get(port_id)
        if not port:
            raise ValueError(f"Output port '{port_id}' not found in node '{self.id}'")
        
        target_nodes = []
        for connection in port.connections:
            target_nodes.append(connection.to_node)
        return target_nodes
    


    def connect_output_to(self, from_port_id, other_node, to_port_id):
        from_port = self.outputs.get(from_port_id)
        to_port = other_node.inputs.get(to_port_id)

        if not from_port:
            raise ValueError(f"Output port '{from_port_id}' not found in node '{self.id}'")
        if not to_port:
            raise ValueError(f"Input port '{to_port_id}' not found in node '{other_node.id}'")
        
        if from_port.node == other_node:
            raise ValueError("Cannot connect a node's output to its own input")
        
        
        outbound_connection = Connection(self, from_port, other_node, to_port)
        from_port.addConnection(outbound_connection)


        #o_port.addConnection(Connection(other_node, to_port, self, from_port))
        to_port.addConnection(outbound_connection)
        return outbound_connection
    

    
    # this is onlt required for computuation of the graph - not for IR generation
    def compute_inputs(self):
         # mark all output ports as dirty
        for output_port in self.get_output_data_ports():
            output_port._isDirty = True

        # fetch input values
        # TODO: I wonder if it's better to compute just updtream data nodes, and not include control nodes here?
        for input_port in self.get_input_data_ports():
            if input_port._isDirty:
                for connection in input_port.connections:
                    print("Computing input for node", self.id, "from", connection.from_port.node.id)
                    source_node = connection.from_port.node
                    # recursively walk up the chanin and compute the source nodes first. 
                    source_node.compute()
                    # in a real implementation, we would fetch the actual data value here
                    input_port.value = connection.from_port.value
                    input_port._isDirty = False

    def precompute(self):
        self.compute_inputs()

    def postcompute(self):
        # mark all output ports as clean
        for output_port in self.get_output_ports():
            output_port._isDirty = False


    # this is checking for cleen DATA inputs only
    def all_inputs_clean(self):
        for input_port in self.get_input_data_ports():
            if input_port._isDirty:
                return False
        return True
    

    def compute(self):
        self.precompute()

        self.postcompute()

       
    
        # if any inputs are still dirty, we cannot compute this node
        # if any input ports have changed then recompute.

        pass  # Placeholder for node computation logic

        
    
class ParamNode(Node):
    def __init__(self, id, type, default_value=None):
        super().__init__(id, type)

        self.add_data_output('value')

        self.default_value = default_value


    def compute(self):
        super().precompute()

        # For a parameter node, we might just set a default value
        self.outputs['value'].value = self.default_value  # Example default value

        super().postcompute()

class AddNode(Node):
    def __init__(self, id, type):
        super().__init__(id, type)

        self.add_data_input('a')
        self.add_data_input('b')
        self.add_data_output('result')


    def compute(self):
        super().precompute()

        if self.all_inputs_clean():
            a = self.inputs['a'].value
            b = self.inputs['b'].value
            self.outputs['result'].value = a + b  # Example operation
        else:
            print("Cannot compute node", self.id, "because inputs are dirty")



        super().postcompute()
    

class LoopNode(Node):
    def __init__(self, id, type):
        super().__init__(id, type)

        self.add_control_input('exec')
        self.add_control_input('loop_in')
        self.add_control_output('next')
        self.add_control_output('completed')

        self.add_data_input('start')
        self.add_data_input('end')
        self.add_data_input('step')
        self.add_data_output('index')

        self.initalized = False

        self.is_loop_node = True

        self.index = 0

    
    def check_end_condition(self):
        if self.index >= self.index_end:
            return True
        
        return False
    
    def initialize_loop(self):
        print("Initializing loop node")
        # make copies of the loop parameters so that they don't change during the loop execution
        for p in self.get_input_data_ports():
            print("  Loop parameter:", p.port_id, "value:", p.value)
        self.index_start = self.get_input_data_port('start').value
        self.index = self.index_start
        self.index_end = self.get_input_data_port('end').value
        self.index_step = self.get_input_data_port('step').value

        self.initalized = True

    
    def increment_loop(self):
        self.index += self.index_step
        print(" ---- Loop index incremented to:", self.index)
       
    

    #TODO: think about where we would add callbacks/hooks for loop body execution to update UI 
    def compute(self):
        print("LoopNode compute call started...")

        super().precompute() #cook input ports

        
        
        if self.get_input_control_port('exec').isActive():
            print("1. Exec port is active, starting loop...")
            self.get_input_control_port('exec').deactivate()
            if not self.initalized:
                print("2. Loopnode not initialized, initializing...")
                self.initialize_loop()
                self.get_output_data_port('index').value = self.index_start
                self.get_output_control_port('next').activate()
                print("Loopnode initialized, starting loop with index:", self.index_start)

        else:
            print("Exec port not active, waiting for exec...")


        
        
        if self.get_input_control_port('loop_in').isActive():
            self.increment_loop()
            self.get_output_data_port('index').setValue(self.index)
            self.get_input_control_port('loop_in').deactivate()
            if self.check_end_condition():
                print("!!!!!!! trying to complete loop")
                self.get_output_control_port('next').deactivate()
                self.get_output_control_port('completed').activate()   
                self.initalized = False 
            else:
                print("######Continuing loop with index:", self.index)
                self.get_output_control_port('next').activate()

        
        
        
        # TODO: dirty flags are wrong. need to fix this.
        super().postcompute()


class MessageNode(Node):
    def __init__(self, id, type):
        super().__init__(id, type)

        self.dataport_msg = self.add_data_input('msg')
        self.controlport_exec = self.add_control_input('exec')
        self.controlport_next = self.add_control_output('next')
 

    def get_dataport_value(self, port):
        return port.connections[0].from_port.value
    
    def compute(self):
        super().precompute()

        # here we're forcing the port to contain a value and cleaning the port.
        # this is a test.

        if self.all_inputs_clean():
            #msg = self.dataport_msg.connections[0].from_port.value
            msg = self.get_dataport_value(self.dataport_msg)
            print("MessageNode:", msg)  # Example action
        else:
            print("Cannot compute node", self.id, "because inputs are dirty")

        self.controlport_next.activate()

        super().postcompute()

class LogNode(Node):
    def __init__(self, id, type):
        super().__init__(id, type)

        self.add_data_input('msg')
        self.add_control_input('exec')

    def compute(self):
        print("LogNode compute called")
        super().precompute()

        # TODO: remvove this later. we're forcing the port to contain a value and cleaning the port.
        # we can use something similar for default values later in case the port isn't connected to anything.
        msgPort = self.inputs['msg']
        msgPort.value = "Hello, World!"  # Example message
        msgPort._isDirty = False

        if self.all_inputs_clean():
            msg = self.inputs['msg'].value
            print("LogNode:", msg)  # Example action
        else:
            print("Cannot compute node", self.id, "because inputs are dirty")

        super().postcompute()


class Connection:
    def __init__(self, from_node, from_port, to_node, to_port):
        self.from_node = from_node
        self.from_port = from_port
        self.to_node = to_node
        self.to_port = to_port

    

class NodePort:
    def __init__(self, node,  port_id, port_type, is_control=False):
        self.node = node
        self.port_type = port_type  # PORT_TYPE_INPUT or PORT_TYPE_OUTPUT or (PORT_TYPE_INPUT | PORT_TYPE_OUTPUT)    
        self.port_id = port_id
        self._isDirty = True # Placeholder for dirty flag. If data changes or reqiuires recompute then set to True
        self.value = None  # Placeholder for data value

        self.connections = []  # List of Connection objects

        if is_control:
            self.port_type |= 0x80  # Set control bit  
    
    def addConnection(self, connection):
        self.connections.append(connection) 
  
    def isDataPort(self):
        return self.port_type & 0x80 == 0
    
    def isControlPort(self):
        return self.port_type & 0x80 != 0
    
    # TODO: might node need
    def isInputPort(self):
        return self.port_type & PORT_TYPE_INPUT
    
    # TODO: might not need
    def isOutputPort(self):
        return self.port_type & PORT_TYPE_OUTPUT
    
    #TODO: might not need
    def isInputOutputPort(self):
        return (self.port_type & PORT_TYPE_INPUTOUTPUT) == PORT_TYPE_INPUTOUTPUT
    



    def setValue(self, value):
        self.value = value
        self._isDirty = True  # Mark as dirty when value changes

    def getValue(self):
        return self.value


# HMMM. do we need these subclasses and do we seperate control/data port types when defining ports on nodes?
class DataPort(NodePort):
    def __init__(self, node, port_id, port_type):
        super().__init__(node, port_id, port_type)


    def setValue(self, value):
        self.value = value
        for connection in self.connections:
            to_port = connection.to_port
            to_port._isDirty = True  # Mark connected input port as dirty when value changes

class ControlPort(NodePort):
    def __init__(self, node, port_id, port_type):
        super().__init__(node, port_id, port_type | 0x80)



    def activate(self):
        for connection in self.connections:
            to_port = connection.to_port
            to_port.setValue(True)
            # Mark the connected input port as active
        # Placeholder for activating control port
        print(f"Activating control port {self.port_id} on node {self.node.id}")

        #self.setValue(True)
    
    def deactivate(self):
        for connection in self.connections:
            to_port = connection.to_port
            to_port.setValue(False)
        # Placeholder for deactivating control port
        print(f"Deactivating control port {self.port_id} on node {self.node.id}")
        self.setValue(False)

    def isActive(self):
        return self.getValue() == True
    








n1 = Node('node1', 'Start')
n1.add_control_output('out1')
n1.add_data_output('data1')
n2 = Node('node2', 'Process')
n2.add_control_input('in1')
n2.add_data_input('data_in1')
n2.add_control_output('out2')
n2.add_data_output('data_out1')
n3 = Node('node3', 'End')
n3.add_control_input('in2')
n3.add_data_input('data_in2')

c1 = n1.connect_output_to('out1', n2, 'in1')
c2 = n1.connect_output_to('data1', n2, 'data_in1')
c3 = n2.connect_output_to('out2', n3, 'in2')
c4 = n2.connect_output_to('data_out1', n3, 'data_in2')
nodes = [n1, n2, n3]
connections = [c1, c2, c3, c4]  

print(len(n1.get_output_ports())) # should be 2 getting 4 instead




# list node inout ports and their connections
for node in nodes:
    print(f"Node {node.id} ({node.type}):")
    for input_port in node.get_input_ports():
        print(f"  Input Port {input_port.port_id} (type: {'Control' if input_port.isControlPort() else 'Data'}):")
        for conn in input_port.connections:
            print(f"    Connected from Node {conn.from_port.node.id} Port {conn.from_port.port_id}")
    for output_port in node.get_output_ports():
        print(f"  Output Port {output_port.port_id} (type: {'Control' if output_port.isControlPort() else 'Data'}):")
        for conn in output_port.connections:
            print(f"    Connected to Node {conn.to_port.node.id} Port {conn.to_port.port_id}")
    print("")

# validate the above connections are correct when traversing from node1 to node3

assert nodes[0].get_output_ports()[0].connections[0].to_port.node.id == 'node2'
assert nodes[0].get_output_ports()[1].connections[0].to_port.node.id == 'node2'
#assert nodes[1].get_output_ports()[0].connections[0].to_port.node.id == 'node3'
print(nodes[1].get_output_ports()[0].connections[0].to_port.node.id)
print(nodes[1].get_output_ports()[0].connections[0].from_port.node.id)
print(nodes[1].get_output_ports()[0].connections[0].to_port.port_id)
assert nodes[1].get_output_ports()[0].connections[0].to_port.node.id == 'node3'
#assert nodes[1].get_output_ports()[1].connections[0].to_port.node.id == 'node3' 


print(nodes[0].get_input_ports())
for p in nodes[0].get_input_ports():
    print(p.port_id, p.port_type)
    for conn in p.connections:
        print("  connected to:", conn.from_port.node.id, conn.from_port.port_id)    


print("--- ")
for p in nodes[0].get_output_ports():
    print(p.port_id, p.port_type)
    for conn in p.connections:
        print("  connected to:", conn.to_port.node.id, conn.to_port.port_id)    

#traverse nodes and print output connections
for node in nodes:
    print(f"Node {node.id} output connections:")
    for output_port in node.get_output_ports():
        for conn in output_port.connections:
            print(f"  Port {output_port.port_id} -> Node {conn.to_port.node.id} Port {conn.to_port.port_id}")   


def visualize_nodes(nodes):
    for node in nodes:
        print(f"Node {node.id} ({node.type}):")
        for input_port in node.get_input_ports():
            for conn in input_port.connections:
                if conn.to_port == input_port:
                    print(f"  Input Port {input_port.port_id} <- Node {conn.from_port.node.id} Port {conn.from_port.port_id}")
        for output_port in node.get_output_ports():
            for conn in output_port.connections:
                if conn.from_port == output_port:
                    print(f"  Output Port {output_port.port_id} -> Node {conn.to_port.node.id} Port {conn.to_port.port_id}")
        print("")


print("Visualizing node connections:")
#visualize_nodes(nodes, connections)
visualize_nodes(nodes)




# Entry Point
start_node = Node('start', 'Start')
start_node.add_control_output('exec')

# The For Loop Node
for_node = Node('loop_1', 'ForLoop')
for_node.add_control_input('exec')
for_node.add_data_input('start')
for_node.add_data_input('end')
for_node.add_data_input('step')
for_node.add_control_output('body')
for_node.add_data_output('index')     # Provides 'i' to the body
for_node.add_control_output('completed')

# Constants for the loop parameters
c_start = Node('c_0', 'ConstInt')     # Value: 0
c_start.add_data_output('val')

c_end = Node('c_5', 'ConstInt')       # Value: 5
c_end.add_data_output('val')

c_step = Node('c_1', 'ConstInt')      # Value: 1
c_step.add_data_output('val')

# The Body: Log the index
log_node = Node('log', 'Log')
log_node.add_control_input('exec')
log_node.add_data_input('msg')

# The Body: Log the index
log_node2 = Node('log', 'Log')
log_node2.add_control_input('exec')
log_node2.add_data_input('msg')

# End Node
end_node = Node('end', 'End')
end_node.add_control_input('exec')


# 2. Connect Everything

# Start -> Loop
start_node.connect_output_to('exec', for_node, 'exec')

# Loop Parameters (0 to 5, step 1)
c_start.connect_output_to('val', for_node, 'start')
c_end.connect_output_to('val', for_node, 'end')
c_step.connect_output_to('val', for_node, 'step')

# Loop Body Wiring
for_node.connect_output_to('body', log_node, 'exec')   # Control flow
for_node.connect_output_to('index', log_node, 'msg')   # Data flow (Log the index)

# this should not show up in the IR as the generator only follows the first body connection
for_node.connect_output_to('body', log_node2, 'exec')   # Control flow
for_node.connect_output_to('index', log_node2, 'msg')   # Data flow (Log the index)

# Loop Exit
for_node.connect_output_to('completed', end_node, 'exec')

#for_node.connect_output_to('completed', for_node, 'start')  # Loop back to start for demonstration. this prob fails IR generation

nodes = [start_node, for_node, c_start, c_end, c_step, log_node, log_node2, end_node]

visualize_nodes(nodes)


class IRGenerator:
    def __init__(self):
        self.instructions = []
        self.temp_counter = 0
        self.label_counter = 0
        self.node_results = {} # Cache for data node results (SSA-like)

    def new_temp(self):
        self.temp_counter += 1
        return f"t{self.temp_counter}"

    def new_label(self, prefix="L"):
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"

    def emit(self, op, *args):
        self.instructions.append(f"{op:<12} {', '.join(map(str, args))}")

    def get_input_node(self, node, port_id):
        """Helper to find the node connected to a specific input port"""
        port = node.inputs.get(port_id)
        if port and port.connections:
            return port.connections[0].from_node
        return None

    def get_next_control_node(self, node, port_id):
        """Helper to find the next control node"""
        port = node.outputs.get(port_id)
        if port and port.connections:
            return port.connections[0].to_node
        return None

    def compile_data_node(self, node):
        """Recursively compile data dependencies"""
        if node.id in self.node_results:
            return self.node_results[node.id]

        result = None

        if node.type == 'ConstInt' or node.type == 'ConstString':
            # In a real app, value would be stored in node.data
            # Here we infer from ID or hardcode for demo
            val = "0"
            if "c_0" in node.id: val = "0"
            elif "c_5" in node.id: val = "5"
            elif "c_1" in node.id: val = "1"
            elif "c0" in node.id: val = "0"
            elif "c5" in node.id: val = "5"
            elif "c1" in node.id: val = "1"
            elif "msg" in node.id: val = '"Hello World"'
            
            result = self.new_temp()
            self.emit("CONST", val, "->", result)

        elif node.type == 'GetVar':
            var_name = "i" # inferred for demo
            result = self.new_temp()
            self.emit("LOAD", var_name, "->", result)

        elif node.type == 'LessThan':
            a = self.compile_data_node(self.get_input_node(node, 'a'))
            b = self.compile_data_node(self.get_input_node(node, 'b'))
            result = self.new_temp()
            self.emit("LT", a, b, "->", result)

        elif node.type == 'Add':
            a = self.compile_data_node(self.get_input_node(node, 'a'))
            b = self.compile_data_node(self.get_input_node(node, 'b'))
            result = self.new_temp()
            self.emit("ADD", a, b, "->", result)

        self.node_results[node.id] = result
        return result

    def compile_control_flow(self, node):
        """Traverse control flow nodes"""
        while node:
            if node.type == 'Start':
                self.emit("ENTRY")
                node = self.get_next_control_node(node, 'exec')

            elif node.type == 'SetVar':
                val = self.compile_data_node(self.get_input_node(node, 'val'))
                var_name = "i" 
                self.emit("STORE", var_name, val)
                node = self.get_next_control_node(node, 'next')

            elif node.type == 'Log':
                msg = self.compile_data_node(self.get_input_node(node, 'msg'))
                self.emit("PRINT", msg)
                node = self.get_next_control_node(node, 'next')

            elif node.type == 'While':
                loop_start = self.new_label("LOOP_START")
                loop_exit = self.new_label("LOOP_EXIT")

                self.emit("LABEL", loop_start)
                
                # Compile Condition
                cond = self.compile_data_node(self.get_input_node(node, 'condition'))
                self.emit("BR_FALSE", cond, loop_exit)

                # Compile Body
                body_node = self.get_next_control_node(node, 'body')
                if body_node:
                    self.compile_control_flow(body_node)
                
                # Loop back
                self.emit("JUMP", loop_start)
                
                # Exit label
                self.emit("LABEL", loop_exit)
                
                # Continue main path
                node = self.get_next_control_node(node, 'exit')
            
            elif node.type == 'ForLoop':
                # 1. Setup
                start_val = self.compile_data_node(self.get_input_node(node, 'start'))
                end_val = self.compile_data_node(self.get_input_node(node, 'end'))
                step_val = self.compile_data_node(self.get_input_node(node, 'step'))
                
                index_var = f"i" # Using 'i' to match existing codegen expectations for now
                
                # 2. Init: index = start
                self.emit("STORE", index_var, start_val)
                
                loop_start = self.new_label("LOOP_START")
                loop_exit = self.new_label("LOOP_EXIT")
                
                self.emit("LABEL", loop_start)
                
                # 3. Condition: index < end
                curr_index_tmp = self.new_temp()
                self.emit("LOAD", index_var, "->", curr_index_tmp)
                
                # Register this temp as the result for the ForLoop node (for 'index' output)
                self.node_results[node.id] = curr_index_tmp
                
                cond_tmp = self.new_temp()
                self.emit("LT", curr_index_tmp, end_val, "->", cond_tmp)
                self.emit("BR_FALSE", cond_tmp, loop_exit)
                
                # 4. Body
                body_node = self.get_next_control_node(node, 'body')
                if body_node:
                    self.compile_control_flow(body_node)
                    
                # 5. Increment: index = index + step
                # We need to load index again to be safe (body might have changed it, though not in this simple case)
                # But we can reuse curr_index_tmp if we assume SSA-ish, but STORE breaks SSA for 'i'.
                # So let's load again or use the temp if we know 'i' wasn't stored to.
                # For safety, let's use the temp we loaded at start of loop.
                next_val_tmp = self.new_temp()
                self.emit("ADD", curr_index_tmp, step_val, "->", next_val_tmp)
                self.emit("STORE", index_var, next_val_tmp)
                
                self.emit("JUMP", loop_start)
                self.emit("LABEL", loop_exit)
                
                # Continue to 'completed' output
                node = self.get_next_control_node(node, 'completed')

            elif node.type == 'End':
                self.emit("HALT")
                node = None # Stop traversal
            
            else:
                print(f"Unknown control node: {node.type}")
                node = None

# Run the generator
generator = IRGenerator()
print("--- Generated IR ---")
generator.compile_control_flow(start_node)
for instr in generator.instructions:
    print(instr)


class PythonCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.current_block_name = None
        self.indent = "    "

    def parse_ir(self, instructions):
        # Pass 1: Group instructions into blocks
        current_block = []
        self.current_block_name = "entry" # Default entry block
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                # Save previous block
                if self.current_block_name:
                    self.blocks[self.current_block_name] = current_block
                
                # Start new block
                self.current_block_name = parts[1]
                current_block = []
            elif op == "ENTRY":
                continue # Just a marker
            else:
                current_block.append(line)
        
        # Save last block
        if self.current_block_name:
            self.blocks[self.current_block_name] = current_block

    def generate(self):
        code = []
        code.append("def generated_program():")
        code.append(f"{self.indent}# Initialize variables")
        code.append(f"{self.indent}i = 0")
        code.append(f"{self.indent}current_block = 'entry'")
        code.append("")
        code.append(f"{self.indent}while True:")
        
        for block_name, instrs in self.blocks.items():
            code.append(f"{self.indent}{self.indent}if current_block == '{block_name}':")
            
            if not instrs:
                code.append(f"{self.indent}{self.indent}{self.indent}return")
                continue

            for line in instrs:
                self._emit_instruction(line, code, level=3)
            
            # If block doesn't end with a jump/return, we need to handle fallthrough
            # (In this specific IR, blocks usually end with jumps, but for safety:)
            last_op = instrs[-1].split()[0] if instrs else ""
            if last_op not in ["JUMP", "BR_FALSE", "HALT"]:
                # Naive fallthrough logic would go here, but our IR is explicit
                pass

        return "\n".join(code)

    def _emit_instruction(self, line, code, level):
        indent = self.indent * level
        
        # Handle CONST specially to preserve string spaces
        if line.strip().startswith("CONST"):
            # Format: CONST val, ->, dest
            parts = line.split('->')
            # parts[0] is "CONST val, "
            # parts[1] is " dest"
            
            val_part = parts[0].strip()
            # Remove "CONST" prefix
            val_part = val_part[5:].strip()
            # Remove trailing comma if present (from IR formatting)
            if val_part.endswith(','):
                val_part = val_part[:-1]
                
            dest = parts[1].replace(',', '').strip()
            code.append(f"{indent}{dest} = {val_part}")
            return

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = parts[1:]
        
        # Remove '->' arrow from args if present
        args = [a for a in args if a != '->']

        if op == "CONST":
            # Should be handled above, but fallback just in case
            val = args[0]
            dest = args[1]
            code.append(f"{indent}{dest} = {val}")

        elif op == "STORE":
            # STORE var val
            var = args[0]
            val = args[1]
            code.append(f"{indent}{var} = {val}")

        elif op == "LOAD":
            # LOAD var dest
            var = args[0]
            dest = args[1]
            code.append(f"{indent}{dest} = {var}")

        elif op == "LT":
            # LT a b dest
            code.append(f"{indent}{args[2]} = {args[0]} < {args[1]}")

        elif op == "ADD":
            # ADD a b dest
            code.append(f"{indent}{args[2]} = {args[0]} + {args[1]}")

        elif op == "PRINT":
            code.append(f"{indent}print({args[0]})")

        elif op == "BR_FALSE":
            # BR_FALSE cond label
            cond = args[0]
            label = args[1]
            code.append(f"{indent}if not {cond}:")
            code.append(f"{indent}{self.indent}current_block = '{label}'")
            code.append(f"{indent}{self.indent}continue")

        elif op == "JUMP":
            # JUMP label
            label = args[0]
            code.append(f"{indent}current_block = '{label}'")
            code.append(f"{indent}continue")

        elif op == "HALT":
            code.append(f"{indent}return")

# --- Usage ---

# 1. Get the IR from previous step
ir_instructions = generator.instructions

# 2. Generate Python Code
py_gen = PythonCodeGenerator()
py_gen.parse_ir(ir_instructions)
python_source = py_gen.generate()

print("\n--- Generated Python Code ---\n")
print(python_source)

print("\n--- Executing Generated Code ---\n")
exec(python_source)



class AssemblyScriptCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.current_block_name = None
        self.indent = "  "

    def parse_ir(self, instructions):
        # Reuse the same parsing logic or similar
        current_block = []
        self.current_block_name = "entry"
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                if self.current_block_name:
                    self.blocks[self.current_block_name] = current_block
                self.current_block_name = parts[1]
                current_block = []
            elif op == "ENTRY":
                continue
            else:
                current_block.append(line)
        
        if self.current_block_name:
            self.blocks[self.current_block_name] = current_block

    def generate(self):
        code = []
        code.append("export function generated_program(): void {")
        code.append(f"{self.indent}// Initialize variables")
        code.append(f"{self.indent}var i: i32 = 0;")
        code.append(f"{self.indent}var current_block: string = 'entry';")
        code.append("")
        code.append(f"{self.indent}while (true) {{")
        
        for block_name, instrs in self.blocks.items():
            code.append(f"{self.indent}{self.indent}if (current_block == '{block_name}') {{")
            
            if not instrs:
                code.append(f"{self.indent}{self.indent}{self.indent}return;")
                code.append(f"{self.indent}{self.indent}}}")
                continue

            for line in instrs:
                self._emit_instruction(line, code, level=3)
            
            # Close block if
            code.append(f"{self.indent}{self.indent}}}")

        code.append(f"{self.indent}}}") # End while
        code.append("}") # End function
        return "\n".join(code)

    def _emit_instruction(self, line, code, level):
        indent = self.indent * level
        
        # Handle CONST specially to preserve string spaces
        if line.strip().startswith("CONST"):
            parts = line.split('->')
            val_part = parts[0].strip()
            val_part = val_part[5:].strip()
            if val_part.endswith(','):
                val_part = val_part[:-1]
            
            dest = parts[1].replace(',', '').strip()
            
            # Simple type inference based on value
            # Check if it looks like a number
            is_number = True
            try:
                float(val_part)
            except ValueError:
                is_number = False
                
            type_decl = "i32" if is_number else "string"
            code.append(f"{indent}let {dest}: {type_decl} = {val_part};")
            return

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = parts[1:]
        args = [a for a in args if a != '->']

        if op == "CONST":
            val = args[0]
            dest = args[1]
            # Simple type inference based on value
            type_decl = "i32" if val.isdigit() else "string"
            code.append(f"{indent}let {dest}: {type_decl} = {val};")

        elif op == "STORE":
            var = args[0]
            val = args[1]
            code.append(f"{indent}{var} = {val};")

        elif op == "LOAD":
            var = args[0]
            dest = args[1]
            code.append(f"{indent}let {dest}: i32 = {var};")

        elif op == "LT":
            code.append(f"{indent}let {args[2]}: boolean = {args[0]} < {args[1]};")

        elif op == "ADD":
            code.append(f"{indent}let {args[2]}: i32 = {args[0]} + {args[1]};")

        elif op == "PRINT":
            code.append(f"{indent}console.log({args[0]}.toString());")

        elif op == "BR_FALSE":
            cond = args[0]
            label = args[1]
            code.append(f"{indent}if (!{cond}) {{")
            code.append(f"{indent}{self.indent}current_block = '{label}';")
            code.append(f"{indent}{self.indent}continue;")
            code.append(f"{indent}}}")

        elif op == "JUMP":
            label = args[0]
            code.append(f"{indent}current_block = '{label}';")
            code.append(f"{indent}continue;")

        elif op == "HALT":
            code.append(f"{indent}return;")

# Usage
as_gen = AssemblyScriptCodeGenerator()
as_gen.parse_ir(ir_instructions)
as_source = as_gen.generate()
print("\n--- Generated AssemblyScript Code (Dispatcher) ---\n")
print(as_source)


class RelooperCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.block_order = []
        self.indent = "  "

    def parse_ir(self, instructions):
        current_block = []
        current_name = "entry"
        self.block_order.append(current_name)
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                if current_name:
                    self.blocks[current_name] = current_block
                current_name = parts[1]
                self.block_order.append(current_name)
                current_block = []
            elif op == "ENTRY":
                continue
            else:
                current_block.append(line)
        
        if current_name:
            self.blocks[current_name] = current_block

    def generate(self):
        code = []
        code.append("export function generated_program_optimized(): void {")
        code.append(f"{self.indent}// Initialize variables")
        code.append(f"{self.indent}var i: i32 = 0;")
        
        # Analyze loops (simple heuristic: block jumps to itself)
        loop_headers = set()
        for name, instrs in self.blocks.items():
            if instrs:
                last_instr = instrs[-1]
                parts = last_instr.split()
                if parts[0] == "JUMP" and parts[1] == name:
                    loop_headers.add(name)

        current_indent_level = 1

        for i, block_name in enumerate(self.block_order):
            instrs = self.blocks.get(block_name, [])
            indent = self.indent * current_indent_level

            # If this block is a loop header, start a loop
            if block_name in loop_headers:
                code.append(f"{indent}while (true) {{")
                current_indent_level += 1
                indent = self.indent * current_indent_level

            for line in instrs:
                self._emit_instruction(line, code, current_indent_level, block_name, loop_headers)

            # If this block was a loop header, close it
            if block_name in loop_headers:
                current_indent_level -= 1
                code.append(f"{self.indent * current_indent_level}}}")

        code.append("}")
        return "\n".join(code)

    def _emit_instruction(self, line, code, level, current_block_name, loop_headers):
        indent = self.indent * level
        
        # Handle CONST specially
        if line.strip().startswith("CONST"):
            parts = line.split('->')
            val_part = parts[0].strip()[5:].strip()
            if val_part.endswith(','): val_part = val_part[:-1]
            dest = parts[1].replace(',', '').strip()
            
            is_number = True
            try: float(val_part)
            except ValueError: is_number = False
            type_decl = "i32" if is_number else "string"
            code.append(f"{indent}let {dest}: {type_decl} = {val_part};")
            return

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = parts[1:]
        args = [a for a in args if a != '->']

        if op == "STORE":
            code.append(f"{indent}{args[0]} = {args[1]};")
        elif op == "LOAD":
            code.append(f"{indent}let {args[1]}: i32 = {args[0]};")
        elif op == "LT":
            code.append(f"{indent}let {args[2]}: boolean = {args[0]} < {args[1]};")
        elif op == "ADD":
            code.append(f"{indent}let {args[2]}: i32 = {args[0]} + {args[1]};")
        elif op == "PRINT":
            code.append(f"{indent}console.log({args[0]}.toString());")
        
        elif op == "BR_FALSE":
            cond = args[0]
            target = args[1]
            # If branching to exit, it's a break
            # We assume if we are in a loop header, and we branch elsewhere, it's a break
            if current_block_name in loop_headers:
                code.append(f"{indent}if (!{cond}) break;")
            else:
                # Fallback for non-loop branches (not fully implemented in this simple version)
                code.append(f"{indent}// Branch to {target} (not implemented in simple relooper)")

        elif op == "JUMP":
            target = args[0]
            if target == current_block_name:
                code.append(f"{indent}continue;")
            else:
                 # If jumping to next block, it's a no-op (fallthrough)
                 pass

        elif op == "HALT":
            code.append(f"{indent}return;")

# Usage Relooper
relooper = RelooperCodeGenerator()
relooper.parse_ir(ir_instructions)
relooper_source = relooper.generate()
print("\n--- Generated AssemblyScript Code (Relooper) ---\n")
print(relooper_source)


class PythonRelooperCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.block_order = []
        self.indent = "    "

    def parse_ir(self, instructions):
        current_block = []
        current_name = "entry"
        self.block_order.append(current_name)
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                if current_name:
                    self.blocks[current_name] = current_block
                current_name = parts[1]
                self.block_order.append(current_name)
                current_block = []
            elif op == "ENTRY":
                continue
            else:
                current_block.append(line)
        
        if current_name:
            self.blocks[current_name] = current_block

    def generate(self):
        code = []
        code.append("def generated_program_optimized():")
        code.append(f"{self.indent}# Initialize variables")
        code.append(f"{self.indent}i = 0")
        
        # Analyze loops
        loop_headers = set()
        for name, instrs in self.blocks.items():
            if instrs:
                last_instr = instrs[-1]
                parts = last_instr.split()
                if parts[0] == "JUMP" and parts[1] == name:
                    loop_headers.add(name)

        current_indent_level = 1

        for i, block_name in enumerate(self.block_order):
            instrs = self.blocks.get(block_name, [])
            indent = self.indent * current_indent_level

            # If this block is a loop header, start a loop
            if block_name in loop_headers:
                code.append(f"{indent}while True:")
                current_indent_level += 1
                indent = self.indent * current_indent_level

            for line in instrs:
                self._emit_instruction(line, code, current_indent_level, block_name, loop_headers)

            # If this block was a loop header, close it (dedent)
            if block_name in loop_headers:
                current_indent_level -= 1

        return "\n".join(code)

    def _emit_instruction(self, line, code, level, current_block_name, loop_headers):
        indent = self.indent * level
        
        # Handle CONST specially
        if line.strip().startswith("CONST"):
            parts = line.split('->')
            val_part = parts[0].strip()[5:].strip()
            if val_part.endswith(','): val_part = val_part[:-1]
            dest = parts[1].replace(',', '').strip()
            code.append(f"{indent}{dest} = {val_part}")
            return

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = parts[1:]
        args = [a for a in args if a != '->']

        if op == "STORE":
            code.append(f"{indent}{args[0]} = {args[1]}")
        elif op == "LOAD":
            code.append(f"{indent}{args[1]} = {args[0]}")
        elif op == "LT":
            code.append(f"{indent}{args[2]} = {args[0]} < {args[1]}")
        elif op == "ADD":
            code.append(f"{indent}{args[2]} = {args[0]} + {args[1]}")
        elif op == "PRINT":
            code.append(f"{indent}print({args[0]})")
        
        elif op == "BR_FALSE":
            cond = args[0]
            target = args[1]
            if current_block_name in loop_headers:
                code.append(f"{indent}if not {cond}:")
                code.append(f"{indent}{self.indent}break")
            else:
                code.append(f"{indent}# Branch to {target} (not implemented)")

        elif op == "JUMP":
            target = args[0]
            if target == current_block_name:
                code.append(f"{indent}continue")
            else:
                 pass

        elif op == "HALT":
            code.append(f"{indent}return")

# Usage Python Relooper
py_relooper = PythonRelooperCodeGenerator()
py_relooper.parse_ir(ir_instructions)
py_relooper_source = py_relooper.generate()
print("\n--- Generated Python Code (Relooper) ---\n")
print(py_relooper_source)

print("\n--- Executing Optimized Python Code ---\n")
exec(py_relooper_source)
generated_program_optimized()









p1 = ParamNode('param1', 'Parameter', 5)
p2 = ParamNode('param2', 'Parameter', 10)

testNode = AddNode('testNode', 'Test')

msgNode = MessageNode('msgNode', 'Message')
logNode = LogNode('logNode', 'Log')

p1.connect_output_to('value', testNode, 'a')
p2.connect_output_to('value', testNode, 'b')

testNode.compute()

testNode.connect_output_to('result', msgNode, 'msg')
msgNode.connect_output_to('next', logNode, 'exec')


result= testNode.outputs["result"].value
print("Result of addition:", result)




s = ParamNode('start', 'Parameter', 0)
e = ParamNode('end', 'Parameter', 5)
step = ParamNode('step', 'Parameter', 1)

loop = LoopNode('loop1', 'Loop')

s.connect_output_to('value', loop, 'start')
e.connect_output_to('value', loop, 'end')
step.connect_output_to('value', loop, 'step')   



loopmessage = MessageNode('msgNode', 'Message')
loop.connect_output_to('index', loopmessage, 'msg')

loop.connect_output_to('next', loopmessage, 'exec')


loopmessage.connect_output_to('next', loop, 'loop_in')

network = NodeNetwork()
network.compute([msgNode])

print(msgNode.get_output_control_ports())
print(msgNode.get_output_ports()[0].port_id)  # should be 'next'
print(msgNode.get_output_ports()[0].port_type)  # should be 'next'


print("Executing Loop Node Network:")
network = NodeNetwork()
loop.get_input_control_port('exec').setValue(True)
network.compute([loop])

#network.compute([loop])

