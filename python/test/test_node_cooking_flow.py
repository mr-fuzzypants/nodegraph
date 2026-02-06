import os
import sys
import asyncio
import pytest
from typing import List, Dict

# Adjust path to find modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from nodegraph.python.core.Node import Node, ExecutionResult, ExecCommand
from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.NodePort import InputControlPort, OutputControlPort, InputDataPort, OutputDataPort, ValueType
from nodegraph.python.core.GraphPrimitives import Edge

# Global execution log to verify order
EXECUTION_LOG = []

# NodeNetwork Removed - Fixes integrated into Core
# class NodeNetwork(NodeNetwork): ...
    

@Node.register("FlowTestNode")
class FlowTestNode(Node):
    def __init__(self, id, type="FlowTestNode", **kwargs):
        super().__init__(id, type, **kwargs)
        self.is_flow_control_node = True
        
        # Standard Flow Ports
        self.inputs["exec"] = InputControlPort(self, "exec")
        self.outputs["next"] = OutputControlPort(self, "next")
        
        # Optional Data Ports
        self.inputs["data_in"] = InputDataPort(self.id, "data_in", ValueType.INT)
        
    async def compute(self, executionContext=None):
        global EXECUTION_LOG
        print(f"COMPUTING FLOW NODE: {self.name}")
        EXECUTION_LOG.append(self.name)
        
        # Determine next nodes based on outgoing connections from 'next'
        # In a real runner, the node might conditionally choose output ports.
        # Here we mock checking the 'next' port.
        next_ids = []
        if self.network:
            edges = self.network.get_outgoing_edges(self.id, "next")
            next_ids = [e.to_node_id for e in edges]
        
        result = ExecutionResult(ExecCommand.CONTINUE)
        """
         "network_id": self.network.id if self.network else None,
            "node_id": self.node.id,
            "node_path:": self.node.get_path(),
        """
        result.network_id = executionContext["network_id"] 
        result.node_id = executionContext["node_id"] 
        result.node_path = executionContext["node_path"] 
        result.uuid = executionContext["uuid"] 
        result.control_outputs["next"] = True  # Activate 'next' port
        result.next_node_ids = next_ids
        return result

@Node.register("DataTestNode")
class DataTestNode(Node):
    def __init__(self, id, type="DataTestNode", **kwargs):
        super().__init__(id, type, **kwargs)
        self.is_flow_control_node = False
        self.outputs["out"] = OutputDataPort(self.id, "out", ValueType.INT)
        self.outputs["out"].value = 100 # Default value
        
    async def compute(self, executionContext=None):
        global EXECUTION_LOG
        print(f"COMPUTING DATA NODE: {self.name}")
        EXECUTION_LOG.append(self.name)

        result = ExecutionResult(ExecCommand.CONTINUE)

        result.network_id = executionContext["network_id"] 
        result.node_id = executionContext["node_id"] 
        result.node_path = executionContext["node_path"] 
        result.uuid = executionContext["uuid"] 
        result.data_outputs["out"] = self.outputs["out"].value 
        return result

@Node.register("MathAddNode")
class MathAddNode(Node):
    def __init__(self, id, type="MathAddNode", **kwargs):
        super().__init__(id, type, **kwargs)
        self.is_flow_control_node = False
        self.inputs["a"] = InputDataPort(self.id, "a", ValueType.INT)
        self.inputs["b"] = InputDataPort(self.id, "b", ValueType.INT)
        self.outputs["sum"] = OutputDataPort(self.id, "sum", ValueType.INT)

    async def compute(self, executionContext=None):
        global EXECUTION_LOG
        val_a = self.inputs["a"].value if self.inputs["a"].value is not None else 0
        val_b = self.inputs["b"].value if self.inputs["b"].value is not None else 0
        
        res = val_a + val_b
        # print(f"COMPUTING DATA NODE: {self.id} = {val_a} + {val_b} = {res}")
        EXECUTION_LOG.append(self.name)

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["sum"] = res
        return result


@NodeNetwork.register("MockSubnetNode")
class MockSubnetNode(NodeNetwork):
    def __init__(self, id, type, network=None, **kwargs):
        super().__init__(id, type,  network=network)
        self.type = "MockSubnetNode"
        self.is_flow_control_node = True
        self.cooking_internally = False

    async def compute(self, executionContext=None):
        global EXECUTION_LOG
        EXECUTION_LOG.append(f"Subnet:{self.name}")
        
        # Delegate actual logic to the base NodeNetwork implementation
        return await super().compute(executionContext=executionContext)



class TestNodeCookingFlow:
    
    def setup_method(self):
        global EXECUTION_LOG
        EXECUTION_LOG.clear()

        #NodeNetwork.all_nodes.clear()  # Reset global registry

        NodeNetwork.deleteAllNodes()
        NodeNetwork.graph.reset()

    def teardown_method(self):
        # Stub: Cleanup logic here
        pass
    
    
    
    def test_flow_linear(self):
        
        #Structure: Start(F) -> Middle(F) -> End(F)
        
        #net = NodeNetwork("net_flow_linear", None)
        net = NodeNetwork.createRootNetwork("net_flow_linear", "NodeNetworkSystem")
        net = NodeNetwork.createRootNetwork("net_flow_linear", "NodeNetworkSystem")
        n1 = net.createNode("Start", "FlowTestNode")
        n2 = net.createNode("Middle", "FlowTestNode")
        n3 = net.createNode("End", "FlowTestNode")
        
        #net.connectNodes("Start", "next", "Middle", "exec")
        net.connectNodesByPath("/net_flow_linear:Start", "next", "/net_flow_linear:Middle", "exec")
        

        #net.connectNodes("Middle", "next", "End", "exec")
        net.connectNodesByPath("/net_flow_linear:Middle", "next", "/net_flow_linear:End", "exec")
        
        asyncio.run(net.cook_flow_control_nodes(n1))
        
        assert EXECUTION_LOG == ["Start", "Middle", "End"]

    def test_flow_branch(self):
     
        #Structure: 
        ##     /-> B(F)
        #A(F)
        #     /-> C(F)
        
        #net = NodeNetwork("net_flow_branch", None)
        net = NodeNetwork.createRootNetwork("net_flow_branch", "NodeNetworkSystem")
        n_a = net.createNode("A", "FlowTestNode")
        n_b = net.createNode("B", "FlowTestNode")
        n_c = net.createNode("C", "FlowTestNode")
        
        #net.connectNodes("A", "next", "B", "exec")
        net.connectNodesByPath("/net_flow_branch:A", "next", "/net_flow_branch:B", "exec")


        #net.connectNodes("A", "next", "C", "exec")
        net.connectNodesByPath("/net_flow_branch:A", "next", "/net_flow_branch:C", "exec")
        
        asyncio.run(net.cook_flow_control_nodes(n_a))
        
        assert "A" in EXECUTION_LOG
        assert "B" in EXECUTION_LOG
        assert "C" in EXECUTION_LOG
        assert EXECUTION_LOG[0] == "A"
        assert len(EXECUTION_LOG) == 3

    
    
    def test_mixed_data_flow(self):
        
        #Structure:
        #           [DataNode]
        #               | (val=100)
        #               v
        #[FlowStart] -> [FlowConsumer]
        #
        #Goal: When FlowConsumer runs, it should trigger DataNode cook if needed.
        #Note: The current simple `cook_flow_control_nodes` mock might not trigger data cooking automatically 
        #unless explicitly coded. This test validates if that requirements is met.
        
        #net = NodeNetwork("net_mixed", None)
        net = NodeNetwork.createRootNetwork("net_mixed", "NodeNetworkSystem")
        flow_start = net.createNode("Start", "FlowTestNode")
        flow_consumer = net.createNode("Consumer", "FlowTestNode")
        data_provider = net.createNode("Provider", "DataTestNode")
        
        # Flow connection
        #net.connectNodes("Start", "next", "Consumer", "exec")
        net.connectNodesByPath("/net_mixed:Start", "next", "/net_mixed:Consumer", "exec")
        
        # Data connection
        #net.connectNodes("Provider", "out", "Consumer", "data_in")
        net.connectNodesByPath("/net_mixed:Provider", "out", "/net_mixed:Consumer", "data_in")
        
        asyncio.run(net.cook_flow_control_nodes(flow_start))
        
        assert "Start" in EXECUTION_LOG
        assert "Consumer" in EXECUTION_LOG
        
        # Verify Data Node execution
        # Depending on implementation:
        # 1. Does FlowConsumer trigger Provider directly?
        # 2. Does cook_flow_control_nodes pre-scan dependencies?
        assert "Provider" in EXECUTION_LOG, "Data provider should be computed when needed by Flow node"
        
        # Order check: Provider should compute before or during Consumer, but definitely before Consumer finishes if it needs data
        # In this simplistic log, we just check presence.
       

    def test_subnetwork_tunneling(self):
        
        #Structure: 
        ##[ExternalData(123)] -> [Subnet In] -> [InternalFlow]
        #
        #The internal flow node needs data from outside the subnet.
        
        #net = NodeNetwork("root", None)
        net = NodeNetwork.createRootNetwork("root", "NodeNetworkSystem")
        subnet_stop = net.createNetwork("subnet_stop")
        
        # External Data
        ext_data = net.createNode("ExtData", "DataTestNode")
        ext_data.outputs["out"].value = 123
        
        # Subnet Ports
        subnet_stop.add_data_input_port("tunnel_data")
        subnet_stop.add_control_input_port("tunnel_exec")
        
        # Internal Logic
        internal_flow = subnet_stop.createNode("InternalFlow", "FlowTestNode")
        
        # Connect: External -> Subnet -> Internal
        # 1. Data: ExtData -> Subnet.tunnel_data -> InternalFlow.data_in
        #net.connectNodes("ExtData", "out", "subnet_stop", "tunnel_data")
        net.connectNodesByPath("/root:ExtData", "out", "/root/subnet_stop", "tunnel_data")

        #subnet_stop.connectNodes("subnet_stop", "tunnel_data", "InternalFlow", "data_in")
        subnet_stop.connectNodesByPath("/root/subnet_stop", "tunnel_data", "/root/subnet_stop:InternalFlow", "data_in")
       

        # 2. Flow: Subnet.tunnel_exec -> InternalFlow.exec
        # Note: We trigger the subnet directly via python for this test
        #subnet_stop.connectNodes("subnet_stop", "tunnel_exec", "InternalFlow", "exec")
        subnet_stop.connectNodesByPath("/root/subnet_stop", "tunnel_exec", "/root/subnet_stop:InternalFlow", "exec")
       
        #net.connectNodesByPath("/root/subnet_stop", "tunnel_exec", "/root/subnet_stop/InternalFlow", "exec")
        
        # Hack to simulate 'calling' the subnet
        # In a real engine, the subnet node itself would be computed, which would delegate to internal graph.
        # Here we just cook the internal node to see if it pulls data through the tunnel.
        asyncio.run(net.cook_flow_control_nodes(internal_flow))
        

        print("EXECUTION LOG:", EXECUTION_LOG)
        assert "InternalFlow" in EXECUTION_LOG
        assert "ExtData" in EXECUTION_LOG, "External data should be cooked via tunnel"
    
    def test_nested_subnetwork_flow(self):
       
        #Structure:
        #Root -> [Subnet A] -> [Subnet B] -> FlowNode
        # Flow passes deeply through hierarchy.
       
        #root = NodeNetwork("root", network=None)
        root = NodeNetwork.createRootNetwork("root", "NodeNetworkSystem")
        subnet_a = root.createNetwork("A")
        subnet_b = subnet_a.createNetwork("B")
        
        leaf_node = subnet_b.createNode("Leaf", "FlowTestNode")
        
        # Ports to hole through
        # Root -> A.in -> B.in -> Leaf.exec
        subnet_a.add_control_input_port("exec")
        subnet_b.add_control_input_port("exec")
        
        # Connections
        # Root level isn't strictly needed if we start cook at Leaf, but let's define structure
        #subnet_a.connectNodes("A", "exec", "B", "exec")
        #subnet_b.connectNodes("B", "exec", "Leaf", "exec")

        root.connectNodesByPath("/root/A", "exec", "/root/A/B", "exec")
        root.connectNodesByPath("/root/A/B", "exec", "/root/A/B:Leaf", "exec")
        
        asyncio.run(root.cook_flow_control_nodes(leaf_node))
        
        assert "Leaf" in EXECUTION_LOG

    """

    """
    def test_nested_subnetwork_outputs(self):
        
        #Structure:
        #Root
        #  |-> Start (Flow)
        #  |-> SubnetA (MockSubnet)
        #        |-> NodeA (Flow)
        #        |-> SubnetB (MockSubnet)
        #              |-> NodeB (Flow)
        #
        #Flow: Start -> SubnetA -> (internal) NodeA -> SubnetB -> (internal) NodeB
        
        #net = NodeNetwork("Root", None)
        net = NodeNetwork.createRootNetwork("Root", "NodeNetworkSystem")
        
        # Level 0
        start = net.createNode("Start", "FlowTestNode")
        #subnet_a = MockSubnetNode("SubnetA", network=net)
        subnet_a = net.createNetwork("SubnetA", "MockSubnetNode")
        #subnet_a = NodeNetwork.create_network("SubnetA", "MockSubnetNode", net)
        #net.add_node(subnet_a)
        
        subnet_a.add_control_input_port("exec")
        
        #net.connectNodes("Start", "next", "SubnetA", "exec")
        net.connectNodesByPath("/Root:Start", "next", "/Root/SubnetA", "exec")

        # Level 1 (Inside SubnetA)
        node_a = subnet_a.createNode("NodeA", "FlowTestNode")
        print("@@@@@@@@@@@@@@@@@@@@@@@@Created NodeA with id:", node_a.id, node_a.name)
    
        #subnet_b = MockSubnetNode("SubnetB", network=subnet_a)
        subnet_b = subnet_a.createNetwork("SubnetB", "MockSubnetNode")
        #subnet_a.add_node(subnet_b)
        
        subnet_b.add_control_input_port("exec")
        
        # Connections inside A: SubnetA.exec -> NodeA -> SubnetB
        subnet_a.connectNodes("SubnetA", "exec", "NodeA", "exec")
        subnet_a.connectNodesByPath("/Root/SubnetA", "exec", "/Root/SubnetA:NodeA", "exec")

        #subnet_a.connectNodes("NodeA", "next", "SubnetB", "exec")
        subnet_a.connectNodesByPath("/Root/SubnetA:NodeA", "next", "/Root/SubnetA/SubnetB", "exec")

        
        # Level 2 (Inside SubnetB)
        node_b = subnet_b.createNode("NodeB", "FlowTestNode")
        
        # Connections inside B: SubnetB.exec -> NodeB
        #subnet_b.connectNodes("SubnetB", "exec", "NodeB", "exec")
        subnet_b.connectNodesByPath("/Root/SubnetA/SubnetB", "exec", "/Root/SubnetA/SubnetB:NodeB", "exec")
        
        # Run
        asyncio.run(net.cook_flow_control_nodes(start))
        
        print("NESTED EXEC LOG:", EXECUTION_LOG)
        
        assert "Start" in EXECUTION_LOG
        assert "Subnet:SubnetA" in EXECUTION_LOG
        assert "NodeA" in EXECUTION_LOG
        assert "Subnet:SubnetB" in EXECUTION_LOG
        assert "NodeB" in EXECUTION_LOG


    
    
    
    def test_subnet_output_flow_and_data(self):
        
        #Structure:
        #Root
        #  |-> Start (Flow)
        #  |-> Subnet (MockSubnet)
        #        |-> InternalFlow (Flow)
        #        |-> InternalData (Data=99)
        #        |-> Subnet.data_out (Port)
        #  |-> End (Flow) uses data from Subnet

        #Flow: Start -> Subnet -> InternalFlow -> Subnet.finished -> End
        #Data: InternalData -> Subnet.data_out -> End.data_in
        
        #net = NodeNetwork("Root", None)
        net = NodeNetwork.createRootNetwork("Root", "NodeNetworkSystem")

        # 1. Outer nodes
        start = net.createNode("Start", "FlowTestNode")
        end = net.createNode("End", "FlowTestNode") # Will read data
        
        #subnet = MockSubnetNode("Subnet", network=net)
        subnet = net.createNetwork("Subnet", "MockSubnetNode")
        #net.add_node(subnet)

        # Outer Subnet Ports
        subnet.add_control_input_port("exec")
        subnet.outputs["finished"] = OutputControlPort(subnet.id, "finished")
        subnet.outputs["data_out"] = OutputDataPort(subnet.id, "data_out", ValueType.INT)

        # Outer Connections
        #net.connectNodes("Start", "next", "Subnet", "exec")
        net.connectNodesByPath("/Root:Start", "next", "/Root/Subnet", "exec")

        #net.connectNodes("Subnet", "finished", "End", "exec")
        net.connectNodesByPath("/Root/Subnet", "finished", "/Root:End", "exec")

        #net.connectNodes("Subnet", "data_out", "End", "data_in")
        net.connectNodesByPath("/Root/Subnet", "data_out", "/Root:End", "data_in")

        
        # 2. Inner Nodes
        internal_flow = subnet.createNode("InternalFlow", "FlowTestNode")
        internal_data = subnet.createNode("InternalData", "DataTestNode")
        internal_data.outputs["out"].value = 99

        # Inner Connections
        # Flow: Subnet.exec -> InternalFlow -> Subnet.finished
        # Note: InternalFlow connects to the Subnet Node (which acts as the sink for 'finished')
        # Wait, 'finished' is an Output on the Subnet (Outer).
        # Inside, it usually appears as a node? Or we connect to the subnet node itself?
        # Convention: Connect to 'subnet.id' and port 'finished'.
        #subnet.connectNodes("Subnet", "exec", "InternalFlow", "exec")
        subnet.connectNodesByPath("/Root/Subnet", "exec", "/Root/Subnet:InternalFlow", "exec")

        #subnet.connectNodes("InternalFlow", "next", "Subnet", "finished")
        subnet.connectNodesByPath("/Root/Subnet:InternalFlow", "next", "/Root/Subnet", "finished")

        # Data: InternalData -> Subnet.data_out
        #subnet.connectNodes("InternalData", "out", "Subnet", "data_out")
        subnet.connectNodesByPath("/Root/Subnet:InternalData", "out", "/Root/Subnet", "data_out")   

        # Run
        asyncio.run(net.cook_flow_control_nodes(start))

        print("SUBNET OUTPUT LOG:", EXECUTION_LOG)

        assert "Start" in EXECUTION_LOG
        assert "Subnet:Subnet" in EXECUTION_LOG
        assert "InternalFlow" in EXECUTION_LOG
        assert "End" in EXECUTION_LOG 
        
        # Verify Execution Order
        # Start -> Subnet -> InternalFlow -> End
        assert EXECUTION_LOG.index("Subnet:Subnet") < EXECUTION_LOG.index("InternalFlow")
        assert EXECUTION_LOG.index("InternalFlow") < EXECUTION_LOG.index("End") # Subnet finishes before End starts? 
        # Actually with MockSubnetNode, it recursively cooks InternalFlow.
        # Then it returns ExecutionResult which triggers End.
        # So yes, InternalFlow should be before End.

        # Verify Data propagation
        # End node doesn't limit execution if data missing in this mock, but we can check values?
        # But 'End' compute doesn't print data inputs.
        # However, MockSubnetNode logic prints "MockSubnet: Propagated data 99"
        
        # Check that the port value on the subnet is correct
        assert subnet.outputs["data_out"].value == 99

    
    
    def test_complex_hierarchical_data_and_flow(self):
        
        #Structure:
        #Root
        #  |-> RootStart (Flow)
        #  |-> RootData (Data=10)
        #  |-> Subnet1 (MockSubnet)
        #        |-> L1_Start (Flow)
        #        |-> L1_LocalData (Data=5)
        #        |-> L1_Op (MathAdd: RootData + L1_LocalData)
        #        |-> Subnet2 (MockSubnet)
        #              |-> L2_Start (Flow)
        #              |-> L2_Result (Data=99)
        #               |-> L2_Consumer (Flow)
        #        |-> Subnet1.out_data <- Subnet2.result_data
        #  |-> RootEnd (Flow)
        
        #net = NodeNetwork("RootSimple", None)
        net = NodeNetwork.createRootNetwork("RootSimple", "NodeNetworkSystem")
    
        # --- Level 0 (Root) ---
        root_start = net.createNode("RootStart", "FlowTestNode")
        root_end = net.createNode("RootEnd", "FlowTestNode")
        root_data = net.createNode("RootData", "DataTestNode")
        root_data.outputs["out"].value = 10
    
        #subnet1 = MockSubnetNode("Subnet1", network=net)
        subnet1 = net.createNetwork("Subnet1", "MockSubnetNode")
        #subnet1 = net.createNetwork("Subnet1", "MockSubnetNode")

        subnet1.add_control_input_port("exec")
        subnet1.add_data_input_port("in_data")
        subnet1.outputs["finished"] = OutputControlPort(subnet1.id, "finished")
        subnet1.outputs["out_data"] = OutputDataPort(subnet1.id, "out_data", ValueType.INT)
        #net.add_node(subnet1)
    
        # Connections Level 0
        #net.connectNodes("RootStart", "next", "Subnet1", "exec")
        net.connectNodesByPath("/RootSimple:RootStart", "next", "/RootSimple/Subnet1", "exec")  

        #net.connectNodes("RootData", "out", "Subnet1", "in_data")
        net.connectNodesByPath("/RootSimple:RootData", "out", "/RootSimple/Subnet1", "in_data")

        #net.connectNodes("Subnet1", "finished", "RootEnd", "exec")
        net.connectNodesByPath("/RootSimple/Subnet1", "finished", "/RootSimple:RootEnd", "exec")

        #net.connectNodes("Subnet1", "out_data", "RootEnd", "data_in")
        net.connectNodesByPath("/RootSimple/Subnet1", "out_data", "/RootSimple:RootEnd", "data_in")

    
        # --- Level 1 (Inside Subnet1) ---
        l1_start = subnet1.createNode("L1_Start", "FlowTestNode")
        l1_local_data = subnet1.createNode("L1_LocalData", "DataTestNode")
        l1_local_data.outputs["out"].value = 5
    
        l1_op = subnet1.createNode("L1_Op", "MathAddNode")
    
        #subnet2 = MockSubnetNode("Subnet2", network=subnet1)
        subnet2 = subnet1.createNetwork("Subnet2", "MockSubnetNode")
        subnet2.add_control_input_port("exec")
        subnet2.add_data_input_port("inner_data")
        subnet2.outputs["finished"] = OutputControlPort(subnet2.id, "finished")
        subnet2.outputs["result_data"] = OutputDataPort(subnet2.id, "result_data", ValueType.INT)
        #subnet1.add_node(subnet2)
    
        # Connections Level 1
        # Flow: Subnet1.exec -> L1_Start -> Subnet2.exec
        #subnet1.connectNodes("Subnet1", "exec", "L1_Start", "exec")
        subnet1.connectNodesByPath("/RootSimple/Subnet1", "exec", "/RootSimple/Subnet1:L1_Start", "exec")   

        #subnet1.connectNodes("L1_Start", "next", "Subnet2", "exec")
        subnet1.connectNodesByPath("/RootSimple/Subnet1:L1_Start", "next", "/RootSimple/Subnet1/Subnet2", "exec")

        #subnet1.connectNodes("Subnet2", "finished", "Subnet1", "finished")
        subnet1.connectNodesByPath("/RootSimple/Subnet1/Subnet2", "finished", "/RootSimple/Subnet1", "finished")
    
        # Data: Subnet1.in_data -> L1_Op.a
        #subnet1.connectNodes("Subnet1", "in_data", "L1_Op", "a")
        subnet1.connectNodesByPath("/RootSimple/Subnet1", "in_data", "/RootSimple/Subnet1:L1_Op", "a")

        # Data: L1_LocalData -> L1_Op.b
        #subnet1.connectNodes("L1_LocalData", "out", "L1_Op", "b")
        subnet1.connectNodesByPath("/RootSimple/Subnet1:L1_LocalData", "out", "/RootSimple/Subnet1:L1_Op", "b")

        # Data: L1_Op.sum -> Subnet2.inner_data
        #subnet1.connectNodes("L1_Op", "sum", "Subnet2", "inner_data")
        subnet1.connectNodesByPath("/RootSimple/Subnet1:L1_Op", "sum", "/RootSimple/Subnet1/Subnet2", "inner_data")
        # Data: Subnet2.result_data -> Subnet1.out_data
        #subnet1.connectNodes("Subnet2", "result_data", "Subnet1", "out_data")
        subnet1.connectNodesByPath("/RootSimple/Subnet1/Subnet2", "result_data", "/RootSimple/Subnet1", "out_data")
    
        # --- Level 2 (Inside Subnet2) ---
        l2_start = subnet2.createNode("L2_Start", "FlowTestNode")
        l2_consumer = subnet2.createNode("L2_Consumer", "FlowTestNode")
        l2_result = subnet2.createNode("L2_Result", "DataTestNode")
        l2_result.outputs["out"].value = 99
    
        # Connections Level 2
        # Flow: Subnet2.exec -> L2_Start -> L2_Consumer -> Subnet2.finished
        #subnet2.connectNodes("Subnet2", "exec", "L2_Start", "exec")
        subnet2.connectNodesByPath("/RootSimple/Subnet1/Subnet2", "exec", "/RootSimple/Subnet1/Subnet2:L2_Start", "exec") 

        #subnet2.connectNodes("L2_Start", "next", "L2_Consumer", "exec")
        subnet2.connectNodesByPath("/RootSimple/Subnet1/Subnet2:L2_Start", "next", "/RootSimple/Subnet1/Subnet2:L2_Consumer", "exec") 


        #subnet2.connectNodes("L2_Consumer", "next", "Subnet2", "finished")
        subnet2.connectNodesByPath("/RootSimple/Subnet1/Subnet2:L2_Consumer", "next", "/RootSimple/Subnet1/Subnet2", "finished")
    
        # Data: Subnet2.inner_data -> L2_Consumer.data_in (Consumption)
        #subnet2.connectNodes("Subnet2", "inner_data", "L2_Consumer", "data_in")
        subnet2.connectNodesByPath("/RootSimple/Subnet1/Subnet2", "inner_data", "/RootSimple/Subnet1/Subnet2:L2_Consumer", "data_in")
    
        # Data: L2_Result -> Subnet2.result_data (Refers to outer port value set)
        #subnet2.connectNodes("L2_Result", "out", "Subnet2", "result_data")
        subnet2.connectNodesByPath("/RootSimple/Subnet1/Subnet2:L2_Result", "out", "/RootSimple/Subnet1/Subnet2", "result_data")
    
        # --- EXECUTE ---
        print("\n--- STARTING COMPLEX TEST ---")
        asyncio.run(net.cook_flow_control_nodes(root_start))
    
        print("COMPLEX EXEC LOG:", EXECUTION_LOG)
    
        # Verifications
        assert "RootStart" in EXECUTION_LOG
        assert "Subnet:Subnet1" in EXECUTION_LOG
        assert "L1_Start" in EXECUTION_LOG
        assert "Subnet:Subnet2" in EXECUTION_LOG
        assert "L2_Start" in EXECUTION_LOG
    
        # Data Node Verification
        assert "L1_Op" in EXECUTION_LOG
        assert "RootData" in EXECUTION_LOG
        assert "L1_LocalData" in EXECUTION_LOG
    
        # Check Values
        assert l1_op.outputs["sum"].value == 15

    

    
    def test_sibling_subnet_data_handoff(self):
        
        #Structure:
        #Root
        #  |-> Producer (MockSubnet)
        #        |-> P_Internal (Data=42)
        #        |-> P_Expose (Tunnel Out)
        #  |-> Consumer (MockSubnet)
        #        |-> C_Receive (Tunnel In)
        #        |-> C_Internal (Data, reads C_Receive)
        # 
        #Flow: RootStart -> Producer -> Consumer
        #Data: Producer.out -> Consumer.in
        #
        #Goal: Verify that data produced in one subnet is correctly 
        #      pushed to the parent and then down into a sibling subnet
        #      BEFORE the sibling subnet executes its internal logic.
       
        #net = NodeNetwork("RootHandoff", None)
        net = NodeNetwork.createRootNetwork("RootHandoff", "NodeNetworkSystem") 
        
        # 1. Producer Subnet
        #producer = MockSubnetNode("Producer", network=net)
        producer = net.createNetwork("Producer", "MockSubnetNode")

        #net.add_node(producer)
        producer.add_control_input_port("exec")
        producer.outputs["finished"] = OutputControlPort(producer.id, "finished")
        producer.outputs["data_out"] = OutputDataPort(producer.id, "data_out", ValueType.INT)
        
        # Producer Internals
        p_data = producer.createNode("P_Internal", "DataTestNode")
        p_data.outputs["out"].value = 42
        # Connect P_Internal to Producer output
        #producer.connectNodes("P_Internal", "out", "Producer", "data_out")
        producer.connectNodesByPath("/RootHandoff/Producer:P_Internal", "out", "/RootHandoff/Producer", "data_out")    

        # NOTE: do not use edge adding helpers here, they may skip internal logic
        #producer.connectNodes("P_Internal", "out", "Producer", "data_out")
        
        # 2. Consumer Subnet
        #consumer = MockSubnetNode("Consumer", network=net)
        consumer = net.createNetwork("Consumer", "MockSubnetNode")

        #net.add_node(consumer)
        consumer.add_control_input_port("exec")
        consumer.add_data_input_port("data_in")
        
        # Consumer Internals
        c_recv = consumer.createNode("C_Receiver", "DataTestNode") 
        # C_Receiver will basically just hold the value, but we need to see if it gets it.
        # Actually DataTestNode computes and sets its output.
        # We need a node that READS the input. MathAddNode is good.
        c_math = consumer.createNode("C_Check", "MathAddNode") # a + b
        
        # Tunnel In: Consumer.data_in -> C_Check.a
        #consumer.connectNodes("Consumer", "data_in", "C_Check", "a")
        consumer.connectNodesByPath("/RootHandoff/Consumer", "data_in", "/RootHandoff/Consumer:C_Check", "a")

        
        # Dummy value for b
        c_const = consumer.createNode("C_Const", "DataTestNode")
        c_const.outputs["out"].value = 0
        #consumer.connectNodes("C_Const", "out", "C_Check", "b")
        consumer.connectNodesByPath("/RootHandoff/Consumer:C_Const", "out", "/RootHandoff/Consumer:C_Check", "b")
        
        # 3. Root Connections
        start = net.createNode("Start", "FlowTestNode")
        
        # Flow: Start -> Producer -> Consumer
        #net.connectNodes("Start", "next", "Producer", "exec")
        net.connectNodesByPath("/RootHandoff:Start", "next", "/RootHandoff/Producer", "exec")   

        #net.connectNodes("Producer", "finished", "Consumer", "exec")
        net.connectNodesByPath("/RootHandoff/Producer", "finished", "/RootHandoff/Consumer", "exec")
        
        # Data: Producer -> Consumer
        #net.connectNodes("Producer", "data_out", "Consumer", "data_in")
        net.connectNodesByPath("/RootHandoff/Producer", "data_out", "/RootHandoff/Consumer", "data_in")
        
        # 4. Internal Execution Triggering
        # We need internal flow nodes to trigger the cooking of data nodes
        # Producer Internal Flow
        p_flow = producer.createNode("P_Flow", "FlowTestNode")
        #producer.connectNodes("Producer", "exec", "P_Flow", "exec")
        producer.connectNodesByPath("/RootHandoff/Producer", "exec", "/RootHandoff/Producer:P_Flow", "exec")

        #producer.connectNodes("P_Flow", "next", "Producer", "finished")
        producer.connectNodesByPath("/RootHandoff/Producer:P_Flow", "next", "/RootHandoff/Producer", "finished")
        
        # Consumer Internal Flow
        c_flow = consumer.createNode("C_Flow", "FlowTestNode")
        #consumer.connectNodes("Consumer", "exec", "C_Flow", "exec")
        consumer.connectNodesByPath("/RootHandoff/Consumer", "exec", "/RootHandoff/Consumer:C_Flow", "exec")
        
        asyncio.run(net.cook_flow_control_nodes( start ))
        
        # Verification
        # 1. Execution Order
        assert "Subnet:Producer" in EXECUTION_LOG
        assert "Subnet:Consumer" in EXECUTION_LOG
        
        # 2. Data Propagation
        print(f"DEBUG: C_Check Input Value: {c_math.inputs['a'].value}")
        assert c_math.inputs["a"].value == 42, "Sibling subnet handoff failed: Data did not propagate from Producer to Consumer."
    