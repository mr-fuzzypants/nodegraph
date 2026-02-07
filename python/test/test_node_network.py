import os
import sys
import logging
import pytest
import asyncio
from typing import Optional, List

# Adjust path to find modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodeNetwork import NodeNetwork, ExecutionResult, ExecutionContext, ExecCommand
from nodegraph.python.core.Types import ValueType
from nodegraph.python.core.GraphPrimitives import Edge
from nodegraph.python.core.NodePort import (
    NodePort, 
    PortDirection, 
    PortFunction, 
    ValueType,
    OutputControlPort,
    InputControlPort,
    OutputDataPort,
    InputDataPort
)

# --- Mocks for Test ---

@Node.register("MockNode")
class MockNode(Node):
    def __init__(self, id, type="MockNode",  *args, **kwargs):
        super().__init__(id, type, *args, **kwargs)
        self.computed = False
        
        # Pre-populate some ports for testing
        self.inputs["in"] = InputControlPort(self.id, "in")
        self.outputs["out"] = OutputControlPort(self.id, "out")
        self.inputs["data_in"] = InputDataPort(self.id, "data_in", ValueType.INT)
        self.outputs["data_out"] = OutputDataPort(self.id, "data_out", ValueType.INT)
    
    async def compute(self):
        self.computed = True
        return ExecutionResult(ExecCommand.CONTINUE, [])

class TestNodeNetwork:

    def setup_method(self):
        # Stub: Setup logic here
        NodeNetwork.deleteAllNodes()
       
        

    def teardown_method(self):
        # Stub: Cleanup logic here
        NodeNetwork.deleteAllNodes()
       

    def test_network_creation(self):
        """Test basic initialization and hierarchy properties"""
        #net = NodeNetwork("net1", None)
        net = NodeNetwork.create_network("net1", "NodeNetworkSystem", None)
        assert net.name == "net1"
        assert net.isNetwork() is True
        assert net.isRootNetwork() is True
        assert len(net.graph.nodes) == 1 # a network is also a node in its own graph


    #def test_add_get_node(self):
    #    """Test adding existing nodes to the network"""
    #    net = NodeNetwork("net1", None)
    #    node = MockNode("n1")
    #    
    #    net.add_node(node)
    #    
    #    assert net.get_node("n1") == node
    #    assert len(net.nodes) == 1
    #    assert net.get_node("nonexistent") is None

    def test_create_node_factory(self):
        """Test creating nodes via the network factory wrapper"""
        #net = NodeNetwork("net1", None)
        net = NodeNetwork.create_network("net1", "NodeNetworkSystem", None)
        
        # Uses the @Node.register("MockNode") above
        node = net.createNode("n1", "MockNode")
        
        assert node.name == "n1"
        assert node.type == "MockNode"
        assert net.get_node_by_name("n1") == node
        
        # Test duplicate ID protection
        with pytest.raises(ValueError):
            net.createNode("n1", "MockNode")

    def test_create_subnetwork(self):
        """Test creating nested networks"""
        #root = NodeNetwork("root", None)
        root = NodeNetwork.create_network("root", "NodeNetworkSystem", None)

        #subnet = root.createNetwork("subnet1")
        subnet = NodeNetwork.create_network("subnet1", "NodeNetworkSystem", root)
        
        assert subnet.name == "subnet1"
        assert subnet.network == root
        assert root.get_node_by_name("subnet1") == subnet
        assert subnet.isSubnetwork() is True
        assert subnet.isRootNetwork() is False
        
        # Ensure deep nesting works
        #subsubnet = subnet.createNetwork("deep_net")
        subsubnet = NodeNetwork.create_network("deep_net", "NodeNetworkSystem", subnet)
        assert subsubnet.network == subnet

    def test_add_network_ports(self):
        """Test adding Tunnel/InputOutput ports to the network boundary"""
        #net = NodeNetwork("net1", None)
        net = NodeNetwork.create_network("net1", "NodeNetworkSystem", None)
        
        in_ctrl = net.add_control_input_port("start")
        in_data = net.add_data_input_port("param")
        
        # Check port properties
        assert "start" in net.inputs
        assert "param" in net.inputs
        
        assert in_ctrl.port_name == "start"
        assert in_ctrl.function == PortFunction.CONTROL
        assert in_ctrl.direction == PortDirection.INPUT_OUTPUT
        
        assert in_data.port_name == "param"
        assert in_data.function == PortFunction.DATA
        assert in_data.direction == PortDirection.INPUT_OUTPUT

    def test_connect_nodes_internal(self):
        """Test connecting two nodes strictly inside the network"""
        #net = NodeNetwork("net_test", None)
        net = NodeNetwork.create_network("net_test", "NodeNetworkSystem", None)

        node_a = net.createNode("A", "MockNode")
        node_b = net.createNode("B", "MockNode")
        
        # Connection: A.out -> B.in
        edge = net.connectNodes("A", "out", "B", "in")
        
        assert isinstance(edge, Edge) or isinstance(edge, tuple)
        assert net.find_node_by_id(edge.from_node_id).name == "A"
        assert edge.from_port_name == "out"
        assert net.find_node_by_id(edge.to_node_id).name == "B"
        assert edge.to_port_name == "in"
        
        # Check edges in Arena
        edges = net.get_outgoing_edges(node_a.id, "out")
        assert len(edges) == 1
        assert edges[0] == edge
        
        edges_in = net.get_incoming_edges(node_b.id, "in")
        assert len(edges_in) == 1

    def test_connect_node_not_found(self):
        #net = NodeNetwork("net_err", None)
        net = NodeNetwork.create_network("net_err", "NodeNetworkSystem", None)

        with pytest.raises(ValueError) as exc:
            net.connectNodes("Missing1", "out", "Missing2", "in")
        assert "does not exist" in str(exc.value)

    def test_connect_network_input_to_internal(self):
        """Test distributing a Network Input to an internal node (Tunnel In)"""
        #net = NodeNetwork("net_tunnel", None)
        net = NodeNetwork.create_network("net_tunnel", "NodeNetworkSystem", None)
        
        internal_node = net.createNode("inner", "MockNode")
        
        # Create Network Boundary Port
        net_input = net.add_control_input_port("sys_start")
        
        # Connect: [Network In] -> [Internal Node In]
        # This calls connect_network_input_to, which now uses add_edge directly
        net.connect_network_input_to("sys_start", internal_node, "in")
        
        # Check edge existence in the Network Arena
        # The 'Tunnel' edge is stored as (NetworkID, PortName) -> (NodeID, PortName)
        edges = net.get_outgoing_edges(net.id, "sys_start")
        assert len(edges) == 1
        edge = edges[0]
        assert edge.from_node_id == net.id
        assert net.find_node_by_id(edge.to_node_id).name == "inner"

    def test_delete_node(self):
        net = NodeNetwork.create_network("root_net", "NodeNetworkSystem", None)
        #net= NodeNetworkRoot("net_del", None)
        #net = NodeNetwork("net_del", None)
        net.createNode("A", "MockNode")
        net.createNode("B", "MockNode")
        net.connectNodes("A", "out", "B", "in")
        
        # this test doesn't make sense if edges are globally stored
        # TODO: do we need local edge tracking per network for this to work?
        assert len(net.graph.edges) == 1
        
        net.deleteNode("A")
        network_path = net.graph.get_path(net.id)
        assert net.get_node_by_path(f"{network_path}:A") is None
        
        # Verify connections cleanup    
        assert len(net.graph.edges) == 0
        
        with pytest.raises(ValueError):
            net.deleteNode("A")

    def test_get_downstream_ports(self):
        """
        Structure:
        [n1 (data_out)] -> [n2 (data_in)]
                        -> [n3 (data_in)]
        """
        #net = NodeNetwork("net_downstream", None)
        net = NodeNetwork.create_network("net_downstream", "NodeNetworkSystem", None)
        n1 = net.createNode("n1", "MockNode")
        n2 = net.createNode("n2", "MockNode")
        n3 = net.createNode("n3", "MockNode")

        # Connect n1 -> n2
        net.connectNodes("n1", "data_out", "n2", "data_in")
        # Connect n1 -> n3
        net.connectNodes("n1", "data_out", "n3", "data_in")

        src_port = n1.outputs["data_out"]
        downstream = net.get_downstream_ports(src_port)

        assert len(downstream) == 2
        assert n2.inputs["data_in"] in downstream
        assert n3.inputs["data_in"] in downstream

    def test_get_downstream_ports_iterative(self):
        """
        Structure:
        [n1 (data_out)] -> [n2 (data_in)]
        [n2 (data_out)] -> [n3 (data_in)]
        We are testing traversal through a node if we want that behavior, 
        but commonly 'get_downstream_ports' implementation depends on if it traverses THRU nodes
        or just follows edges. 
        Revisiting the implementation: Usually it just follows edges from a single port.
        But if 'iterative' implies deep traversal (Tunneling), we test that.
        
        Let's test 'Tunneling' which is the complex case:
        [Network Input Port] -> [Internal Node Input]
        """
        #net = NodeNetwork("net_iterative", None)
        net = NodeNetwork.create_network("net_iterative", "NodeNetworkSystem", None)
        # Simulate a tunneling port (Input/Output behavior)
        # For this test, we might need a node with passthrough ports, 
        # but let's stick to standard edges first to ensure base logic holds.
        
        n1 = net.createNode("n1", "MockNode")
        n2 = net.createNode("n2", "MockNode")
        
        net.connectNodes("n1", "data_out", "n2", "data_in")
        
        src_port = n1.outputs["data_out"]
        # Basic edge following
        ports = net.get_downstream_ports(src_port)
        assert len(ports) == 1
        assert ports[0] == n2.inputs["data_in"]


    def test_get_upstream_ports(self):
        """
        Structure:
        [n1 (data_out)] -> [n3 (data_in)]
        [n2 (data_out)] -> [n3 (data_in)] (If multiple inputs allowed, or just one)
        Let's assume data_in allows multiple for this test or use different ports.
        MockNode only has 'data_in'.
        Let's try 1:1 first.
        """
        #net = NodeNetwork("net_upstream", None)
        net = NodeNetwork.create_network("net_upstream", "NodeNetworkSystem", None)

        n1 = net.createNode("n1", "MockNode")
        n2 = net.createNode("n2", "MockNode")

        net.connectNodes("n1", "data_out", "n2", "data_in")

        target_port = n2.inputs["data_in"]
        upstream = net.get_upstream_ports(target_port)

        assert len(upstream) == 1
        assert upstream[0] == n1.outputs["data_out"]

    def test_get_downstream_ports_tunneling(self):
        """
        Test traversing through a port that is both input and output (Tunneling/Reroute).
        Structure: [n1] -> [relay_port(IO)] -> [n2]
        Uses manual edge creation to ensure topology is set regardless of high-level validation.
        """
        #net = NodeNetwork("root", None)
        net = NodeNetwork.create_network("root", "NodeNetworkSystem", None)
        n1 = net.createNode("n1", "MockNode")
        n2 = net.createNode("n2", "MockNode")
        
        # Relay node
        #relay_node = net.createNetwork("relay") 
        relay_node = NodeNetwork.create_network("relay", "NodeNetworkSystem", net)
        # Add a port that is technically in 'inputs' but has INPUT_OUTPUT direction
        relay_port = relay_node.add_data_input_port("io_port")
        
        # Edge 1: n1 -> relay
        net.add_edge(n1.id, "data_out", relay_node.id, "io_port")
        
        # Edge 2: relay -> n2
        net.add_edge(relay_node.id, "io_port", n2.id, "data_in")
        
        # Test
        src_port = n1.outputs["data_out"]
        downstream = net.get_downstream_ports(src_port)
        
        assert len(downstream) == 1
        assert downstream[0] == n2.inputs["data_in"]

        # With IO included
        downstream_all = net.get_downstream_ports(src_port, include_io_ports=True)
        assert len(downstream_all) == 2
        assert relay_node.inputs["io_port"] in downstream_all

    def test_get_upstream_ports_tunneling(self):
        """
        Test upstream traversing through a port that is both input and output.
        Structure: [n1] -> [relay_port(IO)] -> [n2]
        Test upstream from n2.
        """
        #net = NodeNetwork("root_up", None)
        net = NodeNetwork.create_network("root_up", "NodeNetworkSystem", None)

        n1 = net.createNode("n1", "MockNode")
        n2 = net.createNode("n2", "MockNode")
        
        #relay_node = net.createNetwork("relay") 
        relay_node = NodeNetwork.create_network("relay", "NodeNetworkSystem", net)
        relay_port = relay_node.add_data_input_port("io_port")
        
        # Edge 1: n1 -> relay
        net.add_edge(n1.id, "data_out", relay_node.id, "io_port")
        
        # Edge 2: relay -> n2
        net.add_edge(relay_node.id, "io_port", n2.id, "data_in")
        
        # Test upstream from n2
        target_port = n2.inputs["data_in"]
        upstream = net.get_upstream_ports(target_port)
        
        assert len(upstream) == 1
        assert upstream[0] == n1.outputs["data_out"]


    def test_get_input_port_value(self):
        #net = NodeNetwork("net_val", None)
        net = NodeNetwork.create_network("net_val", "NodeNetworkSystem", None)

        n1 = net.createNode("n1", "MockNode")
        n2 = net.createNode("n2", "MockNode")

        # Connect n1.data_out -> n2.data_in
        net.add_edge(n1.id, "data_out", n2.id, "data_in")

        # Set source value
        n1.outputs["data_out"].value = 99
        
        # Test target
        target_port = n2.inputs["data_in"]
        target_port._isDirty = True # Ensure it tries to fetch
        
        val = net.get_input_port_value(target_port)
        
        assert val == 99
        assert target_port.value == 99
        assert target_port.isDirty() is False

    def test_get_input_port_value_multiple_drivers(self):
        """
        Test behavior when multiple sources drive one input. 
        Current implementation takes the last one and back-propagates to others.
        """
        #net = NodeNetwork("net_multi", None)
        net = NodeNetwork.create_network("net_multi", "NodeNetworkSystem", None)
        n1 = net.createNode("n1", "MockNode")
        print(n1.outputs)
        n2 = net.createNode("n2", "MockNode")
        n3 = net.createNode("n3", "MockNode") # receiver

        print(n1.outputs)

        net.add_edge(n1.id, "data_out", n3.id, "data_in")
        net.add_edge(n2.id, "data_out", n3.id, "data_in")

        n1.outputs["data_out"].value = 10
        n2.outputs["data_out"].value = 20
        
        target_port = n3.inputs["data_in"]
        target_port._isDirty = True
        
        val = net.get_input_port_value(target_port)
        
        # Expect n2 to win because it was added last (LIFO/Stack behavior of pop on list from get_upstream_ports)
        assert val == 20
        assert target_port.value == 20
        
        # Verify specific behavior: overwriting other sources
        assert n1.outputs["data_out"].value == 20 
