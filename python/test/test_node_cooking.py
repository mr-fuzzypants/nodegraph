import os
import sys
import pytest
import asyncio
from typing import List

# Adjust path to find modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from nodegraph.python.core.Node import Node, ExecutionResult, ExecCommand
from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.NodePort import InputDataPort, OutputDataPort
from nodegraph.python.core.Types import ValueType

# Global execution log to verify order
EXECUTION_LOG = []

@Node.register("CookingTestNode")
class CookingTestNode(Node):
    def __init__(self, id, type="CookingTestNode", **kwargs):
        super().__init__(id, type, **kwargs)
        self.compute_count = 0
        # Ensure we have data ports for cook_data_nodes to trace
        self.inputs["in"] = InputDataPort(self.id, "in", ValueType.INT)
        self.outputs["out"] = OutputDataPort(self.id, "out", ValueType.INT)
    
    # Matching the updated signature from previous edits (if any)
    async def compute(self, executionContext=None):
        assert(executionContext is not None), "Execution context must be provided"
        global EXECUTION_LOG

        # TODO: we should be passing in the node name to the conext
        node = self.network.find_node_by_id(executionContext["node_id"])
        EXECUTION_LOG.append(node.name)
        self.compute_count += 1

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.network_id = executionContext["network_id"] 
        result.node_id = executionContext["node_id"] 
        result.node_path = executionContext["node_path"] 
        result.uuid = executionContext["uuid"] 
        result.data_outputs["out"] = self.compute_count
        return result


class TestNodeCooking:
    
    def setup_method(self):
        global EXECUTION_LOG
        EXECUTION_LOG.clear()
        NodeNetwork.deleteAllNodes()

    def teardown_method(self):
        # Stub: Cleanup logic here
        pass

    def test_cook_simple_dependency(self):
        """
        Structural: A -> B
        Goal: cook_data_nodes(B) should trigger A then B.
        """
        #net = NodeNetwork("net_linear", None)
        net = NodeNetwork.createRootNetwork("net_linear", "NodeNetworkSystem")
        node_a = net.createNode("A", "CookingTestNode")
        node_b = net.createNode("B", "CookingTestNode")
        
        #NOTE: DO NOT USE EDGE ADDING HELPERS HERE, THEY MAY SKIP INTERNAL LOGIC
        # Connect A.out -> B.in
        #net.add_edge("A", "out", "B", "in")
        net.connectNodes("A", "out", "B", "in")

        assert net.get_incoming_edges(node_b.id, "in"), "Node B should have incoming edges"
        
        # Action
        asyncio.run(net.cook_data_nodes(node_b))
        
        # Verify
        assert "A" in EXECUTION_LOG, "Upstream node A should have computed"
        assert "B" in EXECUTION_LOG, "Target node B should have computed"
        
        # Verify Order: A must be before B
    
        assert EXECUTION_LOG.index("A") < EXECUTION_LOG.index("B")

    def test_cook_diamond_dependency(self):
        """
        Structural:
             /--> B --/
           A           D
             /-> C --/
             
        Goal: cook_data_nodes(D) -> Toposort: A, {B,C}, D
        """
        #net = NodeNetwork("net_diamond", None)
        net = NodeNetwork.createRootNetwork("net_diamond", "NodeNetworkSystem")
        node_a = net.createNode("A", "CookingTestNode")
        node_b = net.createNode("B", "CookingTestNode")
        node_c = net.createNode("C", "CookingTestNode")
        node_d = net.createNode("D", "CookingTestNode")
        
        net.connectNodes("A", "out", "B", "in")
        net.connectNodes("A", "out", "C", "in")
        net.connectNodes("B", "out", "D", "in")
        
        # we do not allow multiplte edges to the same port in this model
        with pytest.raises(ValueError):
            net.connectNodes("C", "out", "D", "in")

        # NOTE: do not use edge adding helpers here, they may skip internal logic
        #net.add_edge("A", "out", "B", "in")
        #net.add_edge("A", "out", "C", "in")
        #net.add_edge("B", "out", "D", "in")
        #net.add_edge("C", "out", "D", "in")
        
        asyncio.run(net.cook_data_nodes(node_d))
        #asyncio.run(net.cook_flow_control_nodes(node_d))
        assert len(EXECUTION_LOG) == 3
        assert EXECUTION_LOG[0] == "A"
        assert EXECUTION_LOG[-1] == "D"
        assert "B" in EXECUTION_LOG
        #assert "C" in EXECUTION_LOG

    def test_cook_fan_in(self):
        """
        Structural:
           A --\
                C
           B --\
        """
        net = NodeNetwork.createRootNetwork("net_fanin", "NodeNetworkSystem")
        node_a = net.createNode("A", "CookingTestNode")
        node_b = net.createNode("B", "CookingTestNode")
        node_c = net.createNode("C", "CookingTestNode")
        
        net.connectNodes("A", "out", "C", "in")

        # we do not allow multiplte edges to the same port in this model
        with pytest.raises(ValueError):
            net.connectNodes("B", "out", "C", "in")
        # NOTE: do not use edge adding helpers here, they may skip internal logic
        #
        #net.add_edge("A", "out", "C", "in")
        #net.add_edge("B", "out", "C", "in")
        
        asyncio.run(net.cook_data_nodes(node_c))
        
        assert "A" in EXECUTION_LOG
        #assert "B" in EXECUTION_LOG
        assert EXECUTION_LOG[-1] == "C"

    def test_cook_disconnected(self):
        """
        Structural: A   B
        Cook B. A should remain untouched.
        """
        #net = NodeNetwork("net_dis", None)
        net = NodeNetwork.createRootNetwork("net_dis", "NodeNetworkSystem")
        node_a = net.createNode("A", "CookingTestNode")
        node_b = net.createNode("B", "CookingTestNode")
        
        asyncio.run(net.cook_data_nodes(node_b))
        
        assert "B" in EXECUTION_LOG
        assert "A" not in EXECUTION_LOG

    def test_cook_chain_three(self):
        """
        A -> B -> C
        """
        #net = NodeNetwork("net_chain3", None)
        net = NodeNetwork.createRootNetwork("net_chain3", "NodeNetworkSystem")
        a = net.createNode("A", "CookingTestNode")
        b = net.createNode("B", "CookingTestNode")
        c = net.createNode("C", "CookingTestNode")
        
        net.connectNodes("A", "out", "B", "in")
        net.connectNodes("B", "out", "C", "in")
        # NOTE: do not use edge adding helpers here, they may skip internal logic
        #net.add_edge("A", "out", "B", "in")
        #net.add_edge("B", "out", "C", "in")
        
        asyncio.run(net.cook_data_nodes(c))
        #asyncio.run(net.cook_flow_control_nodes(c))
        
        print("EXECUTION_LOG:", EXECUTION_LOG)
        assert EXECUTION_LOG == ["A", "B", "C"]
