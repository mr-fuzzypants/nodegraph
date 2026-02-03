import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from collections import OrderedDict

from nodegraph.python.core.NodePort import *
from nodegraph.python.core.Node import *
from nodegraph.python.core.NodeNetwork import NodeNetwork

from nodegraph.python.noderegistry.NodeRegistry import MessageNode, LoopNode, IfNode, LogNode, AddNode, LessThanNode
from nodegraph.python.compiler.PythonGenerator import PythonGenerator

import logging

# Configure Logging ONCE at the entry point of your application
logging.basicConfig(
    level=logging.INFO,  # Set to DEBUG to see runner internals
    format='[%(asctime)s]:%(name)s:(%(levelname)s) - %(message)s',
    datefmt='%H:%M:%S'
)

# Create Loop Node Network and if the index is less than 10 print out the index value
# Demonstrates:
#  * How to create Nodes:
#       Start Parameter Nodes (Data Nodes)
#       Loop Node (Flow Control Node)
#       If Node (Flow Control Node)
#       LessThan Node (Data  Node)
#       Message Node (Flow Control Node)
#  * How to connect control and data ports between nodes
#  * Initiate execution of the graph.
# 
""""
Flow Breakdown

1. The Loop: Takes parameters (0 to 20, step 1) and drives the process.
    * Data: Emits current index.
    * Control: Emits body execution signal for every iteration.
2. The Condition (Left Side):
    * Checks if index (from loop) is less than 10.
    * Sends a boolean result to the IfNode.
3. The Filter (IfNode):
    * Receives execution signal from Loop.
    * Checks the condition from LessThan.
    * Only passes execution flow to the True port if condition is met.
4. The Output (Right Side):
    * MsgNode receives data directly from the loop (index).
    * But it only executes (prints) when triggered by the IfNode.

       [s: 0]      [e: 20]    [step: 1]
          |           |           |
          v           v           v
       (start)      (end)       (step)
    +-----------------------------------+
    |             LOOP NODE             |
    |              (loop1)              |
    +-----------------------------------+
      | (body)                    | (index)
      | [Control]                 | [Data]
      |                           +--------------------------+-----------------+
      H                           |                          |                 |
      H                           v (a)                      |                 |
      H                    +-------------+                   |                 |
      H                    |  LESSTHAN   |                   |                 |
      H                    | (lessthan1) |                   |                 |
      H                    +-------------+                   |                 |
      H                           ^ (b)                      |                 |
      H                           |                          |                 |
      H                     [const_5: 10]                    |                 |
      v (exec)                    | (result)                 |                 |
    +-----------+                 |                          |                 |
    |  IF NODE  | <(condition)----+                          |                 |
    | (ifnode1) |                                            |                 |
    +-----------+                                            v (msg)           |
      H (true)                                         +-----------+           |
      H [Control]                                      | MSG NODE  |           |
      H==============================================> | (msgNode) | <---------+
      v (exec)                                         +-----------+

"""

print("\n\n")
print("===================================")
print("EXAMPLE 1 - Loop Node Network")
print("\n\n")

network = NodeNetwork("LoopNetwork")

s = network.create_node('start_param', 'Parameter', 0)  # start, end, step parameters
e = network.create_node('end_param', 'Parameter', 20)
step = network.create_node('step_param', 'Parameter', 1)


loop = network.create_node('loop1', 'Loop')

s.connect_output_to('value', loop, 'start')     # inputs to loop node
e.connect_output_to('value', loop, 'end')
step.connect_output_to('value', loop, 'step')   

const_5 = network.create_node('const_5', 'Parameter', 10)
lessthan = network.create_node('lessthan1', 'LessThan')
loop.connect_output_to('index', lessthan, 'a')
const_5.connect_output_to('value', lessthan, 'b')


ifnode = network.create_node('ifnode1', 'If')
lessthan.connect_output_to('result', ifnode, 'condition')
loop.connect_output_to('body', ifnode, 'exec')


loopmessage = network.create_node('msgNode', 'Message')
ifnode.connect_output_to('true', loopmessage, 'exec')
loop.connect_output_to('index', loopmessage, 'msg')




print("Executing Loop Node Network:")

loop.get_input_control_port('exec').setValue(True)  # Trigger the loop

import asyncio
asyncio.run(network.compute([loop]))


from nodegraph.python.compiler.IRBuilder import IRBuilder
# 3. Compile
builder = IRBuilder()

# We compile the 'Effect' node (Printer). 
# It should pull dependencies (Add -> Params) automatically.
print("Compiling chain starting at 'network outer'...")
builder.compile_chain(loop)

builder.print_ir()

print("\n=== GENERATED PYTHON CODE (Example 1) ===")
generator = PythonGenerator(debug=True)
code = generator.generate(builder)
print(code)
print("=== EXECUTING GENERATED CODE ===")
#Execute in a new namespace to avoid collisions
exec_globals = {}
exec(code, exec_globals)
exec_globals['run_program']()


from nodegraph.python.compiler.AssemblyScriptGenerator import AssemblyScriptGenerator
generator = AssemblyScriptGenerator(debug=True)
code = generator.generate(builder)
print("\n=== GENERATED ASSEMBLYSCRIPT CODE (Example 3) ===")
print(code)



"""
    (User Activates)
   net_exec_port.activate()
          |
          v
  +---------------------------------------------------------------+
  |                      NodeNetwork: "MyNetwork"                 |
  |                                                               |
  |    [Input: exec]                         [Input: param_input] |
  |          |                                       ^            |
  |          | (Tunneling Control)                   | (Loopback) |
  |          |                                       |            |
  |          v                                       |            |
  |   +-------------+       +-------------+    +------------+     |
  |   |             |       |             |    | param_node |     |
  |   | INTERNAL    |       | INTERNAL    |    +------------+     |
  |   | MSG NODE 1  |       | MSG NODE 2  |          |            |
  |   |             |       |             |          | (value)    |
  |   +-------------+       +-------------+          |            |
  |          ^   ^              ^   ^                |            |
  |   (exec)-+   +-(msg) (exec)-+   +-(msg)          |            |
  |          |___|__________|___|____________________|            |
  |              |          |                                     |
  |              +----------+                                     |
  |                   | (Tunneling Data)                          |
  |                   +-------------------------------------------+
  +---------------------------------------------------------------+

"""
print("\n\n")
print("===================================")
print("EXAMPLE 2 - Simple Network with Input Tunneling")
print("\n\n")




# Example 2
# 1. Create the main NodeNetwork
network = NodeNetwork("MyNetwork")

# 2. Add the Control Input (Pass-through/Tunnel)
# This port allows control flow to enter the network and trigger internal nodes.
# Note: Using the method exactly as defined in your file (with the typo 'inputouput')
net_exec_port = network.add_control_input_port("exec")

# 3. Add the Param Data Input (Pass-through/Tunnel)
# This port allows data to be passed from outside the network to internal nodes.
net_data_port = network.add_data_input_port("param_input")

# 4. Create the internal Message Node
msg_node = network.createNode("internal_msg_node", "Message")
msg_node2 = network.createNode("internal_msg_node2", "Message")

# 5. Connect the Network's input ports to the internal Message Node's input ports.
# We use .connectTo() directly here because we are connecting an Input to an Input (Tunneling),
# whereas standard node connections are Output-to-Input.

network.connect_network_input_to("exec", msg_node, "exec")
network.connect_network_input_to("exec", msg_node2, "exec")


edges = network.get_outgoing_edges(network.id, "exec")
print(edges[0].to_port_name)


network.connect_network_input_to("param_input", msg_node, "msg")
network.connect_network_input_to("param_input", msg_node2, "msg")

param_node= network.create_node("param_node", "Parameter", "Hello from Network!")
param_node.connect_output_to("value", network, "param_input")



net_exec_port.activate() # Trigger the network execution
asyncio.run(network.compute())

print("+++ Running Network Again +++")
print("next run")
net_exec_port.activate()
asyncio.run(network.compute())

print("Network created successfully.")


from nodegraph.python.compiler.IRBuilder import IRBuilder
# 3. Compile
builder = IRBuilder()

# We compile the 'Effect' node (Printer). 
# It should pull dependencies (Add -> Params) automatically.
print("Compiling chain starting at 'network outer'...")
builder.compile_chain(network)

builder.print_ir()




# Example 2
# 1. Create the main NodeNetwork




"""
       (User Activates)
    net_exec_port_outer
           |
           v
  +-----------------------------------------------------------------------+
  |                     NodeNetwork: "MyNetwork_Outer"                    |
  |                                                                       |
  |   [Outer Input: exec]                      [Outer Input: param_input] |
  |            |                                            ^             |
  |            | (Pass-through)                             |             |
  |            v                                            | (Loopback)  |
  |   +---------------------------------------------------|-----+         |
  |   |              NodeNetwork: "MyNetwork_Inner"       |     |         |
  |   |                                                   |     |         |
  |   |   [Inner Input: exec]      [Inner Input: param_input]   |         |
  |   |            |                           |                |         |
  |   |            |                           +-------+        |         |
  |   |            v                                   |        |         |
  |   |   +----------------+       +----------------+  |        |         |
  |   |   | INTERNAL       |       | INTERNAL       |  |        |         |
  |   |   | MSG NODE 1     |       | MSG NODE 2     |  |        |         |
  |   |   +----------------+       +----------------+  |        |         |
  |   |           ^                        ^           |        |         |
  |   |     (exec)|                  (exec)|           |        |         |
  |   |           +-------+      +---------+           |        |         |
  |   |                   |      |                     |        |         |
  |   |             (msg) |      | (msg)               |        |         |
  |   |                   |      |                     |        |         |
  |   |                   ^      ^                     |        |         |
  |   |                   |      |                     |        |         |
  |   |       +-----------|------|---------------------+        |         |
  |   |       |                                                 |         |
  |   |       +----------< Data Distribution <------------------+         |
  |   |                                                                   |
  |   |                   +--------------+                                |
  |   |                   | param_node   |                                |
  |   |                   | Value: "Hi"  | -------------------------------+
  |   |                   +--------------+        (Feeds Outer Input)
  |   +-----------------------------------------------------------------+
  +-----------------------------------------------------------------------+

 
"""

print("\n\n")
print("===================================")
print("EXAMPLE 3 - Nested Networks")
print("\n\n")

network_outer = NodeNetwork("MyNetwork_Outer")
net_exec_port_outer = network_outer.add_control_input_port("exec")
net_data_port_outer = network_outer.add_data_input_port("param_input")
 


network_inner = NodeNetwork("MyNetwork_Inner")
network_outer.add_node(network_inner)

# 2. Add the Control Input (Pass-through/Tunnel)
# This port allows control flow to enter the network and trigger internal nodes.
# Note: Using the method exactly as defined in your file (with the typo 'inputouput')
net_exec_port_inner = network_inner.add_control_input_port("exec")

net_data_port_inner = network_inner.add_data_input_port("param_input") 



# 4. Create the internal Message Node
msg_node = network_inner.createNode("internal_msg_node", "Message")
msg_node2 = network_inner.createNode("internal_msg_node2", "Message")

# 5. Connect the Network's input ports to the internal Message Node's input ports.
# We use .connectTo() directly here because we are connecting an Input to an Input (Tunneling),
# whereas standard node connections are Output-to-Input.

network_inner.connect_network_input_to("exec", msg_node, "exec")
network_inner.connect_network_input_to("exec", msg_node2, "exec")


network_inner.connect_network_input_to("param_input", msg_node, "msg")
network_inner.connect_network_input_to("param_input", msg_node2, "msg")

param_node= network_outer.create_node("param_node", "Parameter", "Hello from Network!")
param_node.connect_output_to("value", network_outer, "param_input")
network_outer.add_node(network_inner) # Critical: Add inner network to outer network registry
network_outer.connect_network_input_to("exec", network_inner, "exec")
network_outer.connect_network_input_to("param_input", network_inner, "param_input")



net_exec_port_outer.activate() # Trigger the network execution
asyncio.run(network_outer.compute())


from nodegraph.python.compiler.IRBuilder import IRBuilder
# 3. Compile
builder = IRBuilder()

# We compile the 'Effect' node (Printer). 
# It should pull dependencies (Add -> Params) automatically.
print("Compiling chain starting at 'network outer'...")
builder.compile_chain(network_outer)

builder.print_ir()

print("\n=== GENERATED PYTHON CODE (Example 3) ===")
generator = PythonGenerator(debug=True)
code = generator.generate(builder)
print(code)
print("=== EXECUTING GENERATED CODE ===")
exec_globals = {}
exec(code, exec_globals)
exec_globals['run_program']()


from nodegraph.python.compiler.WasmGenerator import WasmGenerator

generator = WasmGenerator(debug=True)
code = generator.generate(builder)
print("\n=== GENERATED WASM CODE (Example 3) ===")
print(code) 


from nodegraph.python.compiler.AssemblyScriptGenerator import AssemblyScriptGenerator
generator = AssemblyScriptGenerator(debug=True)
code = generator.generate(builder)
print("\n=== GENERATED ASSEMBLYSCRIPT CODE (Example 3) ===")
print(code)
