import os
import sys
import asyncio
import pytest
from typing import List, Dict

# Adjust path to find modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.Executor import ExecutionContext, ExecutionResult, ExecCommand, Executor
from nodegraph.python.core.Types import ValueType
from nodegraph.python.core.NodePort import InputControlPort, OutputControlPort, InputDataPort, OutputDataPort

# Define ForLoopNode locally for test
@Node.register("ForLoopNode")
class ForLoopNode(Node):
    def __init__(self, id, type="ForLoopNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        
        # State to track iteration
        self._current_index = None
        
        # Inputs
        self.inputs["exec"] = InputControlPort(self.id, "exec")
        self.inputs["start"] = InputDataPort(self.id, "start", ValueType.INT)
        self.inputs["end"] = InputDataPort(self.id, "end", ValueType.INT)
        
        # Outputs
        self.outputs["loop_body"] = OutputControlPort(self.id, "loop_body")  # Fires every iteration
        self.outputs["completed"] = OutputControlPort(self, "completed")  # Fires when done
        self.outputs["index"] = OutputDataPort(self.id, "index", ValueType.INT)

    async def compute(self, executionContext: Dict) -> ExecutionResult:
        start_val = executionContext["data_inputs"].get("start")
        end_val = executionContext["data_inputs"].get("end")

        print("Execution Context Data Inputs:", executionContext)
        #assert(False)
    
    

        #start_val = await self.inputs["start"].getValue()
        #end_val = await self.inputs["end"].getValue()
        
        if start_val is None: start_val = 0
        if end_val is None: end_val = 0

        # Initialize if this is the first run (or we were reset)
        if self._current_index is None:
            self._current_index = start_val
        
        print(f"Loop Node: index={self._current_index}, end={end_val}")

        # Loop Logic
        if self._current_index < end_val:
            # 1. Update Data Output
            iter_val = self._current_index
            self.outputs["index"].setValue(iter_val)
            
            # 2. Increment Step
            self._current_index += 1
            
            # 3. Fire "Body" and request LOOP_AGAIN
            return ExecutionResult(
                ExecCommand.LOOP_AGAIN, 
                control_outputs={"loop_body": True}
            )
            
        else:
            # Loop Finished
            self._current_index = None # Reset state for next time
            return ExecutionResult(
                ExecCommand.COMPLETED, 
                control_outputs={"completed": True}
            )

@Node.register("CounterNode")
class CounterNode(Node):
    def __init__(self, id, type="CounterNode", network_id=None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.inputs["exec"] = InputControlPort(self.id, "exec")
        self.inputs["val"] = InputDataPort(self.id, "val", ValueType.INT)
        self.count = 0
        self.last_val = -1

    async def compute(self, executionContext=None):
        self.count += 1
        val = await self.inputs["val"].getValue()
        if val is not None:
            self.last_val = val
        print(f"  CounterNode {self.name}: count={self.count}, val={val}")
        return ExecutionResult(ExecCommand.CONTINUE)


class TestLoopNode:
    def test_loop_execution(self):
        async def run_test():
            # net = NodeNetwork("LoopNet", "LoopNet") 
            net = NodeNetwork.createRootNetwork("LoopNet", "NodeNetworkSystem")
            
            # Create Nodes
            # loop_node = ForLoopNode("loop_1", network=net)
            loop_node = net.createNode("loop_1", "ForLoopNode")
            
            # counter = CounterNode("counter_1", network=net)
            counter = net.createNode("counter_1", "CounterNode")
            
            # Set Inputs
            loop_node.inputs["start"].setValue(0)
            loop_node.inputs["end"].setValue(5)
            
            # Create Connections
            # loop.loop_body -> counter.exec
            net.graph.add_edge(loop_node.id, "loop_body", counter.id, "exec")
            
            # loop.index -> counter.val
            net.graph.add_edge(loop_node.id, "index", counter.id, "val")
            
            # Run
            print("\nStarting Loop Test")
            await Executor(net.graph).cook_flow_control_nodes(loop_node)
            print("Loop Test Finished\n")
            
            # Verify
            assert counter.count == 5
            assert counter.last_val == 4
            
        asyncio.run(run_test())

    def test_parallel_loop_branches(self):
        # Test that two branches inside the loop run
        async def run_test():
            net = NodeNetwork.createRootNetwork("ParallelLoopNet", "NodeNetworkSystem")
            
            loop_node = net.createNode("loop_p", "ForLoopNode")
            counter_a = net.createNode("counter_a", "CounterNode")
            counter_b = net.createNode("counter_b", "CounterNode")
            
            loop_node.inputs["start"].setValue(0)
            loop_node.inputs["end"].setValue(3)
            
            # Connect loop_body to BOTH counters
            net.graph.add_edge(loop_node.id, "loop_body", counter_a.id, "exec")
            net.graph.add_edge(loop_node.id, "loop_body", counter_b.id, "exec")
            
            # Connect index to both
            net.graph.add_edge(loop_node.id, "index", counter_a.id, "val")
            net.graph.add_edge(loop_node.id, "index", counter_b.id, "val")
            
            print("\nStarting Parallel Loop Test")
            await Executor(net.graph).cook_flow_control_nodes(loop_node)
            print("Parallel Loop Test Finished\n")
            
            assert counter_a.count == 3
            assert counter_b.count == 3
            assert counter_a.last_val == 2
            assert counter_b.last_val == 2
            
        asyncio.run(run_test())

    def test_nested_loops(self):
        # Test Nested Loops: Outer (3 iterations) -> Inner (2 iterations)
        # Total Inner Executions = 3 * 2 = 6
        async def run_test():
            net = NodeNetwork.createRootNetwork("NestedLoopNet", "NodeNetworkSystem")
            
            # Nodes
            outer_loop = net.createNode("OuterLoop", "ForLoopNode")
            inner_loop = net.createNode("InnerLoop", "ForLoopNode")
            counter = net.createNode("Counter", "CounterNode")
            
            # Config
            outer_loop.inputs["start"].setValue(0)
            outer_loop.inputs["end"].setValue(3) # 0, 1, 2
            
            inner_loop.inputs["start"].setValue(0)
            inner_loop.inputs["end"].setValue(2) # 0, 1
            
            # Connections
            # 1. Outer Loop Body -> Inner Loop Exec
            net.graph.add_edge(outer_loop.id, "loop_body", inner_loop.id, "exec")
            
            # 2. Inner Loop Body -> Counter Exec
            net.graph.add_edge(inner_loop.id, "loop_body", counter.id, "exec")
            
            # 3. Data Connections (Optional logging)
            # We connect inner loop index to counter val just to check last value
            net.graph.add_edge(inner_loop.id, "index", counter.id, "val")

            # Run
            print("\nStarting Nested Loop Test")
            await Executor(net.graph).cook_flow_control_nodes(outer_loop)
            print("Nested Loop Test Finished\n")
            
            # Verify
            # Outer runs 3 times. Each time, Inner runs 2 times.
            # Total counter hits = 3 * 2 = 6
            assert counter.count == 6
            assert counter.last_val == 1 # Last inner index is 1

        asyncio.run(run_test())

